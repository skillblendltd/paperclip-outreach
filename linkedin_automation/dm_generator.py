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
        "m1": (
            "This is M1. Use the THREE-LINE FORMULA exactly:\n"
            "LINE 1 (HOOK, ~80 chars): One specific observation about their business, post, or situation. "
            "Must be something only someone who actually looked at their profile would notice. "
            "This is what shows in the mobile notification preview - make it stop the scroll.\n"
            "LINE 2 (CREDIBILITY, one sentence): Prakash is FROM this world, not visiting it. "
            "Use his dual background - 20 years in software PLUS running a print/promo shop. "
            "Examples: '20 years in software before I crossed over and ran a print/promo shop' or "
            "'Spent two decades building software then moved to the shop floor side of this industry'. "
            "Rotate the phrasing - never use the exact same line twice. "
            "Do NOT name TaggIQ. Do NOT say 'founder'. One sentence only.\n"
            "LINE 3 (INSIDER QUESTION): One question. Must be something only an operator could answer "
            "intelligently. Not yes/no. Designed to surface their real operational pain if answered honestly. "
            "Examples: 'How do you handle rush surcharges when a job lands mid-week and you're already at capacity?' "
            "or 'When a quote goes to order, how many times do those numbers get re-entered before the invoice?' "
            "or 'What does your quote flow look like when a customer wants three different products decorated differently?'\n"
            "TOTAL LENGTH: 300-400 characters maximum. Mobile first - if it's longer, cut it."
        ),
        "m2": (
            "This is M2. They replied to M1. Pick up ONE specific thing they said - reflect it back "
            "with an operator-level observation, then ask one follow-up that goes one layer deeper. "
            "Mirror their energy (short reply = short M2). Do NOT pivot to product yet. 250-350 chars."
        ),
        "m2_cold": (
            "M1 went unanswered. Send a standalone value drop - a short field-level observation about their "
            "world that would resonate with anyone who has lived this. No reference to the unanswered message. "
            "No ask. Just genuine industry insight. 150-200 chars."
        ),
        "m3": (
            "This is M3. Soft probe. Ask one specific question about a pain that TaggIQ directly addresses, "
            "framed as genuine curiosity not a pitch setup. 200-300 chars."
        ),
        "m4": (
            "This is M4. They've engaged and described a real pain. Natural pivot - offer to show something "
            "specific and relevant to what they've described. No product name in the first sentence. "
            "Say things like 'happy to walk you through what we built if it'd be useful - 20 mins, no deck'. 200-280 chars."
        ),
        "m5": (
            "This is M5. Demo invite. Context makes it obvious. Never say 'book a demo' or 'schedule a call'. "
            "Keep it conversational and low-pressure. 150-220 chars."
        ),
        "followup": (
            "Follow-up to an existing thread. Continue naturally. Do NOT re-introduce yourself. "
            "Pick up one specific thing from earlier in the conversation. 150-250 chars."
        ),
        "breakup": (
            "M3 went unanswered. One final message. No guilt, no pressure. Leaves the door open warmly. "
            "Example tone: 'No worries if timing is off - happy to pick this up whenever it makes sense.' "
            "100-150 chars max."
        ),
    }.get(sequence_stage, "Write an appropriate message given the context.")

    prompt = textwrap.dedent(f"""
        Write a LinkedIn DM from Prakash to the following person.

        PRAKASH'S BACKGROUND (this is the most powerful credibility signal - use it):
        - 20 years building enterprise software
        - Crossed over and ran a print/promo shop from the inside: quotes, suppliers, decoration, job tickets, rush orders, margin pressure - the full thing
        - Couldn't find software that understood how a shop actually works, so built TaggIQ
        - NOT affiliated with any specific franchise or distributor - fully independent
        - His unique position: most software people have never run a shop floor. Most shop owners have never shipped software. He's done both.
        - Credibility hook: "20 years in software, then ran a print/promo shop, built TaggIQ because nothing out there got both sides right"
        - Voice: direct, warm, no fluff - operator and software person in the same sentence, without being arrogant about either

        ---
        RECIPIENT:
        Name: {person_name}
        Title: {title}
        Company: {company}

        PROFILE CONTEXT (raw LinkedIn page text - extract what's relevant):
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
        - Output ONLY the message body. No subject line. No preamble like "Here is the message". No commentary.
        - Write exactly what Prakash would type into the LinkedIn message box.
        - Short. 3-5 sentences max for M1/M2/M3. Even shorter for follow-ups.
        - Never use em dashes. Use hyphens with spaces instead.
        - No bullet points. No headers. Plain conversational prose.
        - If the recipient is clearly NOT in print/promo/signage/apparel/branded merch - start output with "NOT A FIT:" and explain briefly. Do not write a fake message.
        - Do not mention TaggIQ by name in M1 or M2.
        - End with something that invites a reply - a genuine question or easy open door.
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
