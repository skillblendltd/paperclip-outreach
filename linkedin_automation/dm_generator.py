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
            "This is M1. The job of M1 is NOT to introduce yourself. It is to make them STOP and REPLY.\n\n"
            "Write like a closer, not a curious peer. The bland 'I saw your post and would love to learn about your operation' DM is DEAD - "
            "ignored 99% of the time. What works in 2026: specific, provocative, low-friction yes/no ask, implies something they are losing right now.\n\n"
            "PICK ONE OF THREE VARIANTS based on what the profile gives you:\n\n"
            "===== VARIANT A: PATTERN INTERRUPT (default - use when their pain is industry-standard) =====\n"
            "LINE 1: A specific operator truth that mirrors a pain they live daily. Use vocabulary they use - "
            "rush surcharges, supplier allocations, decoration zones, PO-to-invoice re-entry, margin bleed, "
            "blank goods, tier pricing, screen vs DTF, color matching, job tickets, production capacity.\n"
            "LINE 2: Binary confirmation ask. 'Is that your world at [Company] too?' or 'Sound familiar?' or "
            "'Ever feel that at [Company]?'\n"
            "WHY IT WORKS: The vocabulary itself proves you are not a SaaS tourist. The yes/no ask removes friction.\n"
            "EXAMPLE for an independent print shop:\n"
            "  'Dirty secret most shop owners I talk to admit: 60% of rush job margin gets eaten by supplier surcharges "
            "that hit AFTER the quote is locked. Ever feel that at [Company]?'\n\n"
            "===== VARIANT B: CONSTRAINT HYPOTHETICAL (best when their business has visible growth/scale) =====\n"
            "LINE 1: 'If [Company] had to [specific outcome] in [tight timeframe], where would you start?'\n"
            "WHY IT WORKS: Forces them to think about their actual bottleneck. They cannot answer with 'no thanks'.\n"
            "EXAMPLES:\n"
            "  'If [Company] had to double quote volume this Q3 without adding headcount, what is the first thing that breaks?'\n"
            "  'If you had to cut quote turnaround at [Company] in half this quarter, what is the bottleneck - "
            "supplier response time, decoration costing, or something else?'\n\n"
            "===== VARIANT C: SOCIAL PROOF + CURIOSITY BAIT (best when you can name a comparable result) =====\n"
            "LINE 1: 'A [specific shop type/region] cut [specific metric] from [X] to [Y] by changing one thing in their [workflow/process].'\n"
            "LINE 2: 'Want me to send what they changed?'\n"
            "WHY IT WORKS: Loss aversion (you might be missing this) + curiosity gap (what is the one thing?) + binary ask.\n"
            "EXAMPLES:\n"
            "  'A 6-person promo shop in Dublin cut their multi-supplier quote turnaround from 2 days to 90 minutes by "
            "killing one specific re-entry point. Want me to send what they changed?'\n"
            "  'A franchise print owner went from re-keying every quote 3 times to 1 by fixing one piece of the PO flow. "
            "Mind if I send the breakdown?'\n\n"
            "===== UNIVERSAL RULES FOR M1 =====\n"
            "- DO NOT lead with 'I spent 20 years in software'. That credibility line was wrong for M1 - it makes you the protagonist, not them. "
            "Save the 20-year story for M2 AFTER they reply.\n"
            "- DO NOT use 'I saw your post...' as an opener. It is a preamble, not a hook. Lead with the OBSERVATION ITSELF, not the act of seeing it.\n"
            "- DO use 'we' and 'I' naturally in the message body (e.g. 'we built', 'I keep hearing', 'I have seen').\n"
            "- USE specific numbers, regions, shop sizes, timeframes - vagueness kills replies.\n"
            "- VOCABULARY is the credibility signal. If a SaaS SDR could write this message, it is wrong.\n"
            "- TOTAL LENGTH: 200-350 chars. The Cristian-style closers that actually convert are SHORTER than the old 3-line formula.\n"
            "- ONE question per message, binary preferred."
        ),
        "m2": (
            "This is M2 - they replied to M1. NOW you can drop the operator credibility (one sentence, max). "
            "Pick up ONE specific thing they said and go deeper. The goal is to get them describing their pain in their own words.\n\n"
            "STRUCTURE:\n"
            "LINE 1: Mirror back the specific thing they said with an operator-level observation - shows you actually read it.\n"
            "LINE 2 (optional, only if it adds value): Drop a one-liner of context. 'I came from this side of the industry - "
            "20 years building software then ran a print/promo shop, so this stuff is familiar.' MAX one sentence.\n"
            "LINE 3: One follow-up that goes a layer deeper into what they said. Could be a yes/no OR a specific operational question.\n\n"
            "RULES:\n"
            "- Mirror their energy. 1-line reply from them = 2-line M2 from you.\n"
            "- Do NOT pivot to product (TaggIQ) yet.\n"
            "- Do NOT change the subject - stay on what THEY brought up.\n"
            "- 200-300 chars max."
        ),
        "m2_cold": (
            "M1 went unanswered after 7 days. Send a SHORT value drop - no reference to the unanswered message, no ask.\n\n"
            "STRUCTURE:\n"
            "A single specific observation about their corner of the industry, with implied loss aversion - "
            "the kind of thing that makes an operator pause and think 'wait, am I doing this wrong?'\n\n"
            "EXAMPLES:\n"
            "  'Pattern I keep seeing in promo shops scaling past 5 people: the day they realize re-entering supplier costs "
            "into the quote is eating 6-8 hours a week, they have already lost a quarter.'\n"
            "  'The shops that built supplier relationships in Q2 are the ones who got allocations through the September squeeze. "
            "The ones who did not spent August chasing stock.'\n\n"
            "RULES:\n"
            "- 150-220 chars.\n"
            "- NO ask. The observation alone is the value.\n"
            "- NO 'just following up' or 'wanted to circle back' - that is template signal."
        ),
        "m3": (
            "This is M3 - the artifact offer. They have not replied or have engaged lightly. "
            "Now offer something specific and concrete - not a demo, an ARTIFACT.\n\n"
            "STRUCTURE:\n"
            "LINE 1: Reference what you have been thinking about (related to the value drop in M2 or their original profile signal).\n"
            "LINE 2: Offer the specific artifact with a binary ask. 'Want me to send the 1-pager?' "
            "'Mind if I send the breakdown?' 'Want a Loom of how that works?'\n\n"
            "WHAT THE ARTIFACT IS:\n"
            "- A 1-pager comparing [their pain] vs [common alternative]\n"
            "- A Loom video showing [the specific thing] in 2 minutes\n"
            "- A calculator that shows their margin leak\n"
            "- A short writeup of how [comparable shop] solved this\n\n"
            "RULES:\n"
            "- 180-260 chars.\n"
            "- Binary ask: yes or no.\n"
            "- Do not pitch TaggIQ as a product yet. The artifact is the wedge."
        ),
        "m4": (
            "This is M4 - the natural pivot to 'let me show you'. They engaged with M2 or M3 and described a real pain. "
            "Offer to show how this works - framed as continuation of the conversation, not a 'next step'.\n\n"
            "STRUCTURE:\n"
            "LINE 1: Acknowledge the specific pain they mentioned.\n"
            "LINE 2: Offer to walk them through what you built around exactly that pain. NOW you can name TaggIQ.\n"
            "LINE 3: Tight time commitment, no deck framing.\n\n"
            "EXAMPLES:\n"
            "  'On the supplier cost re-entry thing you mentioned - that is exactly what we built TaggIQ around. "
            "Happy to show you how it works on a real example - 15 mins, no deck, just the workflow. Useful?'\n\n"
            "RULES:\n"
            "- 200-280 chars.\n"
            "- NEVER 'book a demo' or 'schedule a call' or 'discovery call'.\n"
            "- 'Happy to walk you through', 'Could show you on a real example', 'Worth a quick look' are the right verbs."
        ),
        "m5": (
            "This is M5 - the close. They have implicitly agreed in M4 or are warm. Send the calendar link with specific outcome framing.\n\n"
            "STRUCTURE:\n"
            "LINE 1: What they will see in the call (specific outcome).\n"
            "LINE 2: Calendar link or 'grab a slot here' framing.\n\n"
            "EXAMPLES:\n"
            "  'I will show you the quote-to-invoice flow on a job that mirrors your event work - "
            "you will know within 15 mins if it would change anything for you. Grab a slot: [link]'\n\n"
            "RULES:\n"
            "- 150-220 chars.\n"
            "- Specific outcome, not generic 'see how TaggIQ works'.\n"
            "- Calendar link goes here, not earlier."
        ),
        "followup": (
            "Follow-up to an existing thread. Continue naturally. Do NOT re-introduce yourself. "
            "Pick up one specific thing from earlier in the conversation and add one operator-level observation. 150-250 chars."
        ),
        "breakup": (
            "M3 went unanswered. One final message. No guilt, no pressure. Leaves door open warmly.\n\n"
            "EXAMPLES:\n"
            "  'No worries if timing is off - this industry has a way of being busy every week. "
            "Happy to pick this up whenever it makes sense.'\n"
            "  'Going to stop messaging - know the inbox gets noisy. If anything I sent ever becomes relevant, "
            "happy to pick it up.'\n\n"
            "100-150 chars max. No ask. Just close the loop warmly."
        ),
    }.get(sequence_stage, "Write an appropriate message given the context.")

    prompt = textwrap.dedent(f"""
        Write a LinkedIn DM from Prakash to the following person.

        WHO PRAKASH IS (context for tone, NOT to dump in M1):
        - Spent 20 years building enterprise software, then crossed over and ran a print/promo shop from the inside
        - Knows the shop floor: quotes, suppliers, decoration, job tickets, rush orders, margin pressure
        - Couldn't find software that understood how a shop actually works, so built TaggIQ
        - NOT affiliated with any franchise or distributor - fully independent
        - Voice: direct, no fluff, operator and software person in one - never arrogant about either
        - The 20-year story is held for M2 (after they reply). DO NOT dump it in M1.

        WHO IS BEING TARGETED:
        Owners, founders, GMs of print shops, promo distributors, sign companies, decorated apparel businesses,
        and franchise operators in this space. They are operators, not tech enthusiasts. They are skeptical of
        SaaS pitches and reply only when the message sounds like a peer with actual shop floor experience.

        OPERATOR VOCABULARY (use this language to prove you are not a SaaS tourist):
        rush surcharge, supplier allocation, decoration zone, tier pricing, blank goods, screen print vs DTF vs embroidery,
        decoration setup, color matching, PO-to-invoice re-entry, job ticket, production capacity, margin bleed,
        quote-to-order, supplier feed, decoration costing, white-label store, royalty fee (for franchise), corporate-mandated tools.

        WORDS TO AVOID (SaaS tourist signals):
        platform, solution, streamline, transformation, end-to-end, seamless, leverage, synergize, holistic,
        "I'd love to", "I came across", "just wanted to reach out", "quick chat", "pick your brain",
        "circle back", "touch base", "love to learn more about your operation".

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
        - Short. The whole message must fit on a phone screen without scrolling - this is the strict ceiling.
        - Never use em dashes. Use hyphens with spaces instead.
        - No bullet points. No headers. Plain conversational prose.
        - If the recipient is clearly NOT in print/promo/signage/apparel/branded merch - start output with "NOT A FIT:" and explain briefly. Do not write a fake message.
        - Do NOT mention TaggIQ by name in M1 or M2 unless the user history explicitly asks for it.
        - In M1: NEVER lead with "I spent 20 years..." or "I came from enterprise software..." - that biographical opener is dead in 2026 outreach. Hook FIRST. Save the bio for M2.
        - End with something that triggers a reply - a binary yes/no, a "sound familiar?", or a tight specific question. NEVER a generic "would love to hear your thoughts".
        - ALWAYS end the message with a sign-off on a new line:
              - Prakash
              taggiq.com
          (two short lines, lowercase taggiq.com, no marketing tagline)
          This is non-negotiable. The recipient gets the message in their inbox with no other context.
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
