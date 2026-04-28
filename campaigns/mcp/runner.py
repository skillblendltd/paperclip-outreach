"""Reusable Claude-with-MCP runner. The single entry point any Paperclip
code uses to invoke Claude with MCP tools available.

Phase A scope:
  - Wraps subprocess.run() of the Claude CLI with --mcp-config JSON
  - Captures session-level summary (cost, turns, duration) via
    `--output-format json` result mode
  - Writes one MCPSession row per invocation
  - Per-tool MCPActionLog rows are DEFERRED to Phase B (requires
    `--output-format stream-json` parsing)

Phase B will switch to stream-json and populate MCPActionLog. The schema
is already defined; no migration needed at that point.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional

from django.utils import timezone

from campaigns.mcp import config_builder

logger = logging.getLogger(__name__)


CLAUDE_CLI = os.environ.get('PAPERCLIP_CLAUDE_CLI', 'claude')

# Default model when caller doesn't specify. Matches existing handle_replies
# default ('sonnet' is the alias for claude-sonnet-4-6 in our deployments).
DEFAULT_MODEL_FLAG = 'sonnet'

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_TURNS = 30


@dataclass
class MCPRunResult:
    """Outcome of a Claude+MCP invocation."""
    success: bool
    text: str = ''                       # final response text
    error: str = ''
    session_id: str = ''                 # MCPSession.id (str)
    cost_usd: Decimal = Decimal('0')
    duration_ms: int = 0
    num_turns: int = 0
    servers_loaded: list = field(default_factory=list)
    servers_skipped: list = field(default_factory=list)


def run_with_mcp(
    *,
    prompt: str,
    organization,
    allowed_slugs: Iterable[str],
    triggered_by: str,
    prospect=None,
    inbound_email=None,
    model_flag: str = DEFAULT_MODEL_FLAG,
    allowed_tools: str = 'Bash,Read,Write,Edit,Glob,Grep',
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    extra_env: Optional[dict] = None,
    cwd: Optional[str] = None,
) -> MCPRunResult:
    """Run Claude CLI with MCP servers attached and capture audit summary.

    Falls back gracefully when `allowed_slugs` is empty / no eligible
    connections — the call still runs without MCP and an MCPSession with
    server_slugs=[] is recorded so the audit trail is uniform.
    """
    from campaigns.models import MCPSession

    started = time.monotonic()
    cwd = cwd or os.getenv('PAPERCLIP_REPO_DIR', '/app')

    # Step 1 — build MCP config (or get None if no servers).
    build = config_builder.build_for_org(organization, allowed_slugs)

    # Step 2 — open the MCPSession row up-front so partial failures still audit.
    session = MCPSession.objects.create(
        organization=organization,
        prospect=prospect,
        inbound_email=inbound_email,
        triggered_by=triggered_by[:64],
        server_slugs=[c.slug for c in build.connections],
        claude_model=model_flag,
    )

    # Step 3 — assemble argv.
    argv = [
        CLAUDE_CLI,
        '--model', model_flag,
        '--allowedTools', allowed_tools,
        '--max-turns', str(max_turns),
        '--output-format', 'json',
        '-p', prompt,
    ]
    if build.config_path:
        argv.extend(['--mcp-config', build.config_path])

    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    env['PAPERCLIP_MCP_SESSION_ID'] = str(session.id)

    # Step 4 — execute.
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return _finalize(session, started, success=False,
                         error=f'timeout_after_{timeout_seconds}s',
                         build=build)
    except Exception as exc:
        logger.exception('mcp.runner: subprocess crashed')
        return _finalize(session, started, success=False,
                         error=f'subprocess_crash: {exc}',
                         build=build)
    finally:
        # Always remove the MCP config file (it contains secrets).
        if build.config_path:
            try:
                os.unlink(build.config_path)
            except OSError:
                pass

    if proc.returncode != 0:
        err = (proc.stderr or '')[:1000]
        return _finalize(session, started, success=False,
                         error=f'claude_exit_{proc.returncode}: {err}',
                         build=build, raw_stdout=proc.stdout)

    # Step 5 — parse the JSON result envelope.
    result = _parse_json_result(proc.stdout)
    return _finalize(
        session,
        started,
        success=not result.get('is_error', False),
        text=result.get('result', '') or '',
        error='',
        build=build,
        cost_usd=Decimal(str(result.get('total_cost_usd', 0) or 0)),
        num_turns=int(result.get('num_turns', 0) or 0),
        raw_stdout=proc.stdout,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _parse_json_result(stdout: str) -> dict:
    """The Claude CLI in --output-format json mode returns a JSON object on
    stdout. If parsing fails we return an empty dict and the caller treats
    it as success-with-empty-text (the run completed; we just can't audit)."""
    if not stdout:
        return {}
    stdout = stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Fall back: maybe the CLI wrote multiple JSON objects (stream-json).
        # Take the last well-formed one.
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and ('result' in obj or 'is_error' in obj):
                    return obj
            except json.JSONDecodeError:
                continue
        return {}


def _finalize(session, started, *, success, build,
              text='', error='', cost_usd=Decimal('0'),
              num_turns=0, raw_stdout='') -> MCPRunResult:
    duration_ms = int((time.monotonic() - started) * 1000)

    session.success = bool(success)
    session.error_message = (error or '')[:2000]
    session.duration_ms = duration_ms
    session.num_turns = num_turns
    session.total_cost_usd = cost_usd
    session.save(update_fields=[
        'success', 'error_message', 'duration_ms', 'num_turns',
        'total_cost_usd', 'updated_at',
    ])

    return MCPRunResult(
        success=bool(success),
        text=text or '',
        error=error or '',
        session_id=str(session.id),
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        num_turns=num_turns,
        servers_loaded=[c.slug for c in build.connections],
        servers_skipped=[(c.slug, r) for c, r in build.skipped],
    )
