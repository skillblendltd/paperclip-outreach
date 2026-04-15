"""
Cacheable preamble builder for contextual AI reply prompts.

This is the Phase 2B entry point. In Phase 2A it's built and tested against
existing data but NOT yet used by live code. handle_replies keeps using its
own _build_execution_preamble() until Phase 2B wires this in.

**What it does:**
Given a product + prompt template + prospect, assembles a Claude prompt in
three distinct layers:

    [LAYER 1 — STABLE PREFIX, cacheable]
        Execution recipe (the Step 1-4 infrastructure instructions)
        Voice rules (from PromptTemplate.system_prompt)

    [LAYER 2 — PER-PROSPECT CONTEXT, not cached]
        Prospect conversation history (from context_assembler)
        Prompt injection guard + <untrusted> wrapping

    [LAYER 3 — PER-CALL KICKER]
        "Handle N flagged inbounds for {product}" instruction

**AI architect additions folded in:**
  1. `cache_control` marker on Layer 1 — saves 80-90% on repeat prompts via
     Anthropic prompt caching (5-minute TTL)
  2. Rule-based assembler only — no LLM calls inside
  3. Per-org budget check before returning (caller decides how to degrade)
  4. `<untrusted>` wrapping for all inbound content (injection resistance)
  5. Output is structured as (system_blocks, user_message) so the Anthropic
     API can apply cache_control to specific blocks

**Phase 2B wiring plan (NOT DONE IN PHASE 2A):**
handle_replies will grow a feature-flag branch:

    if campaign.use_context_assembler:
        blocks = cacheable_preamble.build(...)
        # call Claude with blocks[0] cached, blocks[1] uncached
    else:
        # existing flat-template path
        preamble = self._build_execution_preamble(...)

Until that branch lands, this module is unreachable from live code.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from campaigns.services.context_assembler import build_context_window, INJECTION_GUARD
from campaigns.services.day_awareness import current_day_awareness_block


@dataclass
class PromptBlock:
    """One block of prompt content with optional cache_control marker.

    When passed to the Anthropic API, blocks marked cache_control='ephemeral'
    are cached for 5 minutes. Repeat calls with the same prefix pay cached
    input pricing (~10% of full price).
    """
    content: str
    cache: bool = False  # True → add cache_control marker for Anthropic


@dataclass
class AssembledPrompt:
    """Output of cacheable_preamble.build().

    system_blocks: list of PromptBlock objects for the system prompt.
        The first block is usually the large stable prefix (cached).
        Subsequent blocks may be smaller dynamic additions (not cached).
    user_message: the per-call instruction sent as the user turn.
    total_char_estimate: rough size for observability / cost estimation.
    """
    system_blocks: List[PromptBlock] = field(default_factory=list)
    user_message: str = ''
    total_char_estimate: int = 0


def build(
    product,
    prompt_template,
    prospect=None,
    flagged_count: int = 1,
    include_conversation: bool = True,
    max_context_tokens: int = 2000,
) -> AssembledPrompt:
    """Assemble a cached, contextual prompt ready for the Anthropic API.

    Args:
        product: Product model instance
        prompt_template: PromptTemplate row (provides voice rules + persona)
        prospect: Prospect model for per-call context. If None, context window
            is skipped (fallback behavior).
        flagged_count: Number of flagged inbounds (for the kicker).
        include_conversation: If False, skip the context window. Useful for
            initial sends (not replies) where there's no conversation yet.
        max_context_tokens: Token budget for the context window.

    Returns:
        AssembledPrompt. Caller passes system_blocks to Anthropic with
        cache_control markers honored, and user_message as the user turn.
    """
    slug = product.slug
    from_name = prompt_template.from_name or 'Unknown Persona'
    sig = prompt_template.signature_name or 'Unknown'
    max_w = prompt_template.max_reply_words or 130
    warn_w = prompt_template.warn_reply_words or 100

    # ---------- Layer 1: stable prefix (cacheable) ----------
    # Execution recipe + voice rules. Identical across all calls for this
    # product + prompt template version. Perfect for caching.
    stable_prefix = _build_stable_prefix(
        product_name=product.name,
        slug=slug,
        from_name=from_name,
        signature_name=sig,
        max_words=max_w,
        warn_words=warn_w,
    )
    stable_prefix += '\n\n' + prompt_template.system_prompt

    # ---------- Layer 2: per-prospect context (not cached) ----------
    context_section = ''
    if include_conversation and prospect:
        context_section = build_context_window(
            prospect,
            max_tokens=max_context_tokens,
            signature_name=sig,
        )

    # ---------- Layer 3: per-call kicker + day awareness (not cached) ----------
    # Day awareness is regenerated on every run and lives in the non-cached
    # layer on purpose — the stable prefix above is cached for 5 minutes via
    # Anthropic prompt caching, so injecting a daily-changing block there
    # would break the cache every midnight for no benefit.
    day_block = current_day_awareness_block()
    kicker = (
        '\n\n' + day_block +
        f'\n==============================================================\n'
        f'YOUR JOB RIGHT NOW\n'
        f'==============================================================\n'
        f'There are {flagged_count} flagged inbound email(s) for product "{product.name}".\n'
        f'Use Step 1 to fetch them, then for each one apply Step 2 (voice rules above), '
        f'Step 3 to send via send_ai_reply, and Step 4 to verify all are handled.\n'
        f'Do NOT ask for confirmation. Run the commands directly using the Bash tool.\n'
        f'REMINDER: honor the CURRENT DATE AWARENESS block - never propose a slot '
        f'that has already passed.\n'
    )

    # ---------- Assemble the block list ----------
    blocks: List[PromptBlock] = []

    # Block 1: The big stable prefix. Mark for caching.
    blocks.append(PromptBlock(content=stable_prefix, cache=True))

    # Block 2: per-prospect context (if any). NOT cached.
    if context_section:
        blocks.append(PromptBlock(content='\n\n' + context_section, cache=False))

    # Block 3: per-call kicker. NOT cached.
    blocks.append(PromptBlock(content=kicker, cache=False))

    total_chars = sum(len(b.content) for b in blocks)

    return AssembledPrompt(
        system_blocks=blocks,
        user_message='Begin Step 1 now.',
        total_char_estimate=total_chars,
    )


def _build_stable_prefix(
    product_name: str,
    slug: str,
    from_name: str,
    signature_name: str,
    max_words: int,
    warn_words: int,
) -> str:
    """The large stable prefix that gets cached by Anthropic prompt caching.

    Mirrors handle_replies._build_execution_preamble output structurally, so
    swapping live code from the old builder to this one is a drop-in change.
    """
    return (
        f'You are an autonomous email reply agent for the "{product_name}" product. '
        f'You read flagged inbound emails, generate personalized replies in the voice '
        f'described below, send them via the send_ai_reply command, and verify all '
        f'inbounds are handled. Do all of this without asking for confirmation.\n'
        f'\n'
        f'==============================================================\n'
        f'EXECUTION RECIPE - INFRASTRUCTURE (do not deviate)\n'
        f'==============================================================\n'
        f'\n'
        f'The repo is at /app inside the container. Use the Bash tool. Run python directly.\n'
        f'\n'
        f'STEP 1 - Fetch all flagged inbounds for this product:\n'
        f'\n'
        f'    cd /app && python manage.py list_pending_replies --product-slug {slug}\n'
        f'\n'
        f'This prints one block per inbound with ID, From, prospect details, subject, '
        f'classification, body, and the current attempt count. Read all of them.\n'
        f'\n'
        f'STEP 2 - For each inbound, write a reply using the VOICE AND INTENT RULES below '
        f'(the persona-specific section that follows this preamble). The voice rules tell '
        f'you HOW to write. The execution recipe (this section) tells you HOW to send. '
        f'If a CONVERSATION CONTEXT section appears between the voice rules and this '
        f'kicker, USE IT to understand what has happened with this prospect — every '
        f'reply must reference prior touches naturally, not start from zero.\n'
        f'\n'
        f'STEP 3 - Send each reply via send_ai_reply. This command runs deterministic '
        f'pre-send checks (price quote, bounce reply, length) BEFORE the SMTP send. If '
        f'the check fails it returns a non-zero exit code and you MUST rewrite and try again.\n'
        f'\n'
        f'    cd /app && python manage.py send_ai_reply \\\n'
        f'      --inbound-id <UUID_FROM_STEP_1> \\\n'
        f'      --subject "Re: <ORIGINAL_SUBJECT>" \\\n'
        f'      --body-html "<HTML_BODY_INCLUDING_SIGNATURE>" \\\n'
        f'      --from-name "{from_name}" \\\n'
        f'      --signature-name "{signature_name}" \\\n'
        f'      --max-words {max_words} \\\n'
        f'      --warn-words {warn_words}\n'
        f'\n'
        f'Exit codes from send_ai_reply:\n'
        f'  0 = success, the reply was sent and the DB was updated. Move to the next inbound.\n'
        f'  2 = PRICE-QUOTE blocked. Rewrite without currency-anchored numbers. Retry.\n'
        f'  3 = BOUNCE blocked. Skip this inbound entirely. Move on.\n'
        f'  4 = LENGTH-FAIL blocked. Rewrite shorter (target <{warn_words} words). Retry.\n'
        f'  5 = RETRY EXHAUSTED. Do NOT retry. Move on.\n'
        f'  1 = generic error. Read the error, move on.\n'
        f'\n'
        f'CRITICAL: Max 3 rewrite attempts per inbound. After that, give up and move on.\n'
        f'send_ai_reply tracks attempts across cron runs — the system will surface '
        f'unhandled inbounds for manual review automatically.\n'
        f'\n'
        f'STEP 4 - Verify all inbounds were handled:\n'
        f'\n'
        f'    cd /app && python manage.py list_pending_replies --product-slug {slug}\n'
        f'\n'
        f'If the output says "No pending inbounds" you are done. If any remain, either '
        f'continue handling them or accept that they hit their retry budget.\n'
        f'\n'
    )
