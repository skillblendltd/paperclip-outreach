"""Build a Claude CLI --mcp-config JSON file from OrgMCPConnections.

Inputs:
  - organization (Organization)         — required, scopes connection lookup
  - allowed_slugs (list of OrgMCPConnection.slug strings)
                                        — pre-filtered set the caller wants
                                          to expose (e.g. union of campaigns'
                                          mcp_servers within a Product)

Output:
  - path to a temp JSON file in the format Claude CLI expects:
      { "mcpServers": { "<slug>": { "type": "...", ... } } }
  - list of OrgMCPConnection objects that landed in the config (for audit)
  - list of skipped connections + reasons (for log lines)

Filtering applied:
  - is_active=True
  - last_health_status != 'down' OR last_health_check older than 1h ago
    (circuit breaker recovery)
  - auth_secret_ref env var is actually set (no point loading a server we
    can't authenticate)

Cross-tenant safety: this function only ever queries connections WHERE
organization=<organization>. Mismatch would be a programming error, not a
runtime check.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import timedelta
from typing import Iterable, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

CIRCUIT_BREAKER_RECOVERY_MINUTES = 60


def build_for_org(
    organization,
    allowed_slugs: Iterable[str],
    *,
    output_path: Optional[str] = None,
) -> 'BuildResult':
    """Build a Claude CLI MCP config JSON file for `organization`, exposing
    only OrgMCPConnections whose slug is in `allowed_slugs`.

    Returns BuildResult with .config_path (None if no servers landed),
    .connections (the loaded ones), .skipped (list of (conn, reason)).
    """
    from campaigns.models import OrgMCPConnection
    from campaigns.mcp.registry import default_tools_for

    allowed = list({s for s in allowed_slugs if s})  # dedupe + drop empties
    if not allowed:
        return BuildResult(config_path=None, connections=[], skipped=[],
                           reason='no_servers_requested')

    qs = OrgMCPConnection.objects.filter(
        organization=organization,
        slug__in=allowed,
        is_active=True,
    ).select_related('server')

    loaded = []
    skipped = []
    now = timezone.now()
    cutoff = now - timedelta(minutes=CIRCUIT_BREAKER_RECOVERY_MINUTES)

    mcp_servers_block: dict = {}
    for conn in qs:
        if conn.last_health_status == 'down' and conn.last_health_check_at and conn.last_health_check_at > cutoff:
            skipped.append((conn, 'circuit_breaker_open'))
            continue

        auth_type = getattr(conn, 'auth_type', 'static_bearer') or 'static_bearer'

        # OAuth-CLI: tokens live in /root/.claude/ (user-scope MCP added via
        # `claude mcp add --user`). The CLI inherits these alongside any
        # servers we add via --mcp-config, so we DO NOT add this server to
        # our JSON. Just count it as loaded for audit.
        if auth_type == 'oauth_cli':
            if not conn.cli_user_scope_name:
                skipped.append((conn, 'oauth_cli_no_scope_name'))
                continue
            loaded.append(conn)
            continue

        # static_bearer / none: build the JSON entry as before.
        secret = ''
        if auth_type == 'static_bearer':
            secret = _resolve_secret(conn.auth_secret_ref)
            if conn.auth_secret_ref and not secret:
                skipped.append((conn, f'secret_unresolved:{conn.auth_secret_ref}'))
                continue

        entry = _build_server_entry(conn, secret)
        if entry is None:
            skipped.append((conn, 'unsupported_transport'))
            continue
        mcp_servers_block[conn.slug] = entry
        loaded.append(conn)

    # `loaded` may include oauth_cli connections even when mcp_servers_block
    # is empty — those are valid (CLI inherits them). Only return None when
    # NOTHING loaded at all.
    if not loaded:
        return BuildResult(config_path=None, connections=[], skipped=skipped,
                           reason='no_eligible_connections')

    if not mcp_servers_block:
        # All loaded are oauth_cli; nothing to write to --mcp-config.
        return BuildResult(config_path=None, connections=loaded, skipped=skipped,
                           reason='ok_oauth_cli_only')

    payload = {'mcpServers': mcp_servers_block}

    # Write to a tempfile we own; caller deletes after subprocess returns.
    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            prefix=f'mcp_{organization.slug}_', suffix='.json',
        )
        os.close(fd)
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    os.chmod(output_path, 0o600)  # secrets present, restrict perms

    return BuildResult(
        config_path=output_path,
        connections=loaded,
        skipped=skipped,
        reason='ok',
    )


def effective_tool_allowlist(connection) -> list[str]:
    """Return the effective tool allowlist for a connection.

    Falls back to the registry default if `enabled_tools` is empty.
    """
    from campaigns.mcp.registry import default_tools_for
    if connection.enabled_tools:
        return list(connection.enabled_tools)
    return default_tools_for(connection.server.slug)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

class BuildResult:
    __slots__ = ('config_path', 'connections', 'skipped', 'reason')

    def __init__(self, config_path, connections, skipped, reason):
        self.config_path = config_path
        self.connections = connections
        self.skipped = skipped
        self.reason = reason

    def __repr__(self):
        return (
            f'BuildResult(path={self.config_path}, '
            f'loaded={[c.slug for c in self.connections]}, '
            f'skipped={[(c.slug, r) for c, r in self.skipped]}, '
            f'reason={self.reason})'
        )


def _resolve_secret(ref: str) -> str:
    """Resolve a secret reference to its actual value. Empty if not found.

    Phase A supports env var refs only. AWS Secrets Manager references
    (arn:aws:secretsmanager:...) are deferred to Phase C+.
    """
    if not ref:
        return ''
    if ref.startswith('arn:aws:secretsmanager:'):
        logger.warning('mcp.config_builder: Secrets Manager refs not yet '
                       'supported; ref=%s', ref)
        return ''
    # Treat as env var name
    return os.environ.get(ref, '') or ''


def _build_server_entry(conn, secret: str) -> Optional[dict]:
    """Translate one OrgMCPConnection into the JSON block Claude CLI expects.

    Returns None if the transport isn't supported.
    """
    server = conn.server
    cfg = dict(conn.connection_config or {})

    if server.transport == 'http' or server.transport == 'streamable_http':
        # HTTP MCP server with bearer auth via Authorization header.
        url = cfg.get('url', '').strip()
        if not url:
            return None
        headers = dict(cfg.get('headers') or {})
        if secret and 'Authorization' not in headers:
            headers['Authorization'] = f'Bearer {secret}'
        entry = {
            'type': 'streamable_http' if server.transport == 'streamable_http' else 'http',
            'url': url,
        }
        if headers:
            entry['headers'] = headers
        return entry

    if server.transport == 'sse':
        url = cfg.get('url', '').strip()
        if not url:
            return None
        entry = {'type': 'sse', 'url': url}
        if secret:
            entry['headers'] = {'Authorization': f'Bearer {secret}'}
        return entry

    if server.transport == 'stdio':
        command_template = cfg.get('command') or server.default_command_template
        if not command_template:
            return None
        # Split into argv. Allow caller to pre-split via cfg['args'].
        if 'args' in cfg:
            command = cfg.get('command_bin', 'npx')
            args = list(cfg.get('args') or [])
        else:
            parts = command_template.split()
            if not parts:
                return None
            command, args = parts[0], parts[1:]
        env = dict(cfg.get('env') or {})
        if secret and conn.auth_secret_ref:
            # Pass the secret through under its original env-var name so the
            # spawned MCP process picks it up.
            env[conn.auth_secret_ref] = secret
        entry = {
            'type': 'stdio',
            'command': command,
            'args': args,
        }
        if env:
            entry['env'] = env
        return entry

    return None
