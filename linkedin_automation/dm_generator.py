"""
DM message generator.

Reads the linkedin-gtm-director skill prompt + reference files,
feeds them plus the prospect's profile context to Claude (via the
same `claude -p` subprocess path the main pipeline uses), and
returns a ready-to-send message string.

The output is ONLY the message body - no preamble, no commentary,
no "Here is the message:". Just the words Prakash will send.
"""

from __future__ import annotations

import json
import logging
import subprocess
import textwrap
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Location of the linkedin-gtm-director skill
SKILL_DIR = Path.home() / ".claude" / "skills" / "linkedin-gtm-director"
SKILL_FILE = SKILL_DIR / "SKILL.md"
REF_DIR = SKILL_DIR / "references"

CLAUDE_CLI = "claude"
GENERATION_MODEL = "sonnet"
GENERATION_TIMEOUT_SEC = 60


def _load_skill_system_prompt() -> str:
    """
    Build a system prompt from the skill file + all reference files.
    Mirrors how the Claude Code runtime loads a skill.
    """
    parts = []

    if SKILL_FILE.exists():
        raw = SKILL_FILE.read_text()
        # Strip frontmatter (--- ... ---) before the actual prompt
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                raw = raw[end + 3:].lstrip()
        parts.append(raw)
    else:
        logger.warning(f"Skill file not found: {SKILL_FILE}")

    if REF_DIR.exists():
        for ref_file in sorted(REF_DIR.glob("*.md")):
            content = ref_file.read_text()
            parts.append(f"\n\n---\n## Reference: {ref_file.stem}\n\n{content}")

    return "\n".join(parts)


def _build_generation_prompt(
    *,
    person_name: str,
    company: str,
    title: str,
    profile_snapshot: str,
    conversation_history: str,
    sequence_stage: str,
    extra_context: str,
) -> str:
    """
    Build the user-turn prompt that asks Claude to write the DM.
    """
    stage_guide = {
        "m1": "This is a FIRST MESSAGE (M1 opener) to a cold prospect you just connected with. Warm, curious, no product pitch.",
        "m2": "This is M2 - a value drop / insight share. Still no ask. Generous, peer-level.",
        "m3": "This is M3 - a soft probe. Ask one genuine question about their operation.",
        "m4": "This is M4 - a natural pivot. Only if they've engaged. Offer to share more or show something, low pressure.",
        "m5": "This is M5 - a demo invite. Only because context makes it obvious. Conversational, specific.",
        "followup": "This is a follow-up to an existing thread. Continue the natural conversation. Do NOT re-introduce yourself or re-explain anything from prior messages.",
    }.get(sequence_stage, "Write an appropriate message given the context.")

    prompt = textwrap.dedent(f"""
        Write a LinkedIn DM from Prakash to the following person.

        ---
        RECIPIENT:
        Name: {person_name}
        Title: {title}
        Company: {company}

        PROFILE CONTEXT:
        {profile_snapshot or "(not available)"}

        CONVERSATION HISTORY (most recent last):
        {conversation_history or "(no prior messages - this is the first contact)"}

        ADDITIONAL CONTEXT FROM PRAKASH:
        {extra_context or "(none)"}

        ---
        STAGE: {sequence_stage.upper()}
        INSTRUCTION: {stage_guide}

        ---
        OUTPUT RULES:
        - Output ONLY the message body. No subject line. No "Here is the message". No commentary.
        - Write exactly what Prakash would type into the LinkedIn message box.
        - Short. 3-5 sentences maximum for openers. Even shorter for follow-ups.
        - Never use em dashes. Use hyphens with spaces instead.
        - No bullet points. No headers. Plain conversational prose.
        - Do not mention TaggIQ by name in M1 or M2 unless the profile makes it obvious.
        - End with something that invites a reply naturally - a question or an easy open door.
    """).strip()

    return prompt


def generate_dm(
    *,
    person_name: str,
    company: str = "",
    title: str = "",
    profile_snapshot: str = "",
    conversation_history: str = "",
    sequence_stage: str = "m1",
    extra_context: str = "",
) -> Optional[str]:
    """
    Generate a LinkedIn DM using the linkedin-gtm-director skill prompt.

    Returns the message string, or None if generation failed.
    """
    system_prompt = _load_skill_system_prompt()
    user_prompt = _build_generation_prompt(
        person_name=person_name,
        company=company,
        title=title,
        profile_snapshot=profile_snapshot,
        conversation_history=conversation_history,
        sequence_stage=sequence_stage,
        extra_context=extra_context,
    )

    cmd = [
        CLAUDE_CLI,
        "--model", GENERATION_MODEL,
        "--max-turns", "1",
        "--output-format", "text",
        "--system-prompt", system_prompt,
        "-p", user_prompt,
    ]

    logger.info(f"Generating {sequence_stage} DM for {person_name} at {company}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GENERATION_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"Claude timed out generating DM for {person_name}")
        return None
    except FileNotFoundError:
        logger.error("claude CLI not found. Make sure it is on PATH.")
        return None

    if result.returncode != 0:
        logger.error(f"Claude exit {result.returncode}: {result.stderr[:300]}")
        return None

    message = (result.stdout or "").strip()
    if not message:
        logger.error("Claude returned empty output")
        return None

    logger.info(f"Generated message ({len(message)} chars) for {person_name}")
    return message
