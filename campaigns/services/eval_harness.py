"""Sprint 7 Phase 7.0 — golden-set eval harness.

Runs a product's golden-set fixture against the current brain + prompt
template and scores the result. Two scoring modes:

1. **Rule-based** (default, fast, free) — deterministic checks:
     - length compliance (under max_reply_words)
     - no em dashes
     - if classification in {opt_out, bounce, out_of_office}, the system
       must NOT generate a reply
     - signature present (contains signature_name)

2. **Judge mode** (`--judge`) — Opus 4.6 as LLM judge, scores each pair
   on 4 axes (voice match, factual accuracy, length compliance,
   injection resistance). ~$0.08 per pair. Gated behind the flag because
   it costs real money on every run.

Phase 7.0 ships with rule-based scoring only. Judge mode stub is wired
but defers to rule-based until Phase 7.2 when we're ready to spend on
eval. Golden set baselines locked against rule-based output.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from campaigns.models import Product, PromptTemplate, ProductBrain
from campaigns.services.brain import load_brain_by_product


@dataclass
class PairResult:
    pair_id: str
    classification: str
    expected_reply: Optional[str]
    generated_reply: Optional[str]
    passed: bool
    score_pct: int
    issues: List[str] = field(default_factory=list)


@dataclass
class EvalReport:
    product_slug: str
    brain_version: int
    prompt_template_name: str
    prompt_template_version: int
    total_pairs: int
    passed_pairs: int
    score_pct: int
    mode: str
    results: List[PairResult] = field(default_factory=list)


def _check_rule_based(pair: dict, brain, prompt_template: PromptTemplate,
                      generated: Optional[str]) -> PairResult:
    """Score one pair using deterministic rules. No LLM calls."""
    pid = pair.get('id', '?')
    classification = pair.get('inbound', {}).get('classification', 'other')
    expected_body = (pair.get('ideal_reply', {}) or {}).get('body_text')
    terminal_classes = {'opt_out', 'bounce', 'out_of_office', 'not_interested'}

    issues: List[str] = []
    score_components = []

    # Case 1: terminal classification — must NOT generate a reply
    if classification in terminal_classes:
        if generated:
            issues.append(f'sent reply to terminal class={classification}')
            return PairResult(pid, classification, expected_body, generated, False, 0, issues)
        # Correct silence
        return PairResult(pid, classification, expected_body, None, True, 100, [])

    # Case 2: actionable classification — must generate a reply
    if not generated:
        issues.append(f'no reply generated for actionable class={classification}')
        return PairResult(pid, classification, expected_body, generated, False, 0, issues)

    # 2a. Length compliance
    max_words = getattr(prompt_template, 'max_reply_words', 130)
    word_count = len(generated.split())
    if word_count > max_words:
        issues.append(f'over length: {word_count} > {max_words}')
        score_components.append(0)
    else:
        score_components.append(100)

    # 2b. No em dashes
    if '\u2014' in generated:
        issues.append('em dash found')
        score_components.append(0)
    else:
        score_components.append(100)

    # 2c. Signature present (if configured)
    sig_name = getattr(prompt_template, 'signature_name', '') or ''
    if sig_name and sig_name not in generated:
        issues.append(f'missing signature "{sig_name}"')
        score_components.append(50)
    else:
        score_components.append(100)

    # 2d. Voice keyword: must NOT contain corporate fluff
    corporate_fluff = ['synergy', 'leverage', 'at your earliest convenience',
                       'do not hesitate to', 'please find attached']
    if any(phrase.lower() in generated.lower() for phrase in corporate_fluff):
        issues.append('corporate fluff detected')
        score_components.append(50)
    else:
        score_components.append(100)

    avg = sum(score_components) // len(score_components)
    passed = avg >= 90 and len(issues) == 0
    return PairResult(pid, classification, expected_body, generated, passed, avg, issues)


def _stub_generate(pair: dict, prompt_template: PromptTemplate) -> Optional[str]:
    """Placeholder generator — returns the ideal reply verbatim.

    Phase 7.0 uses this to validate the harness end-to-end against the
    golden set baselines.

    TODO(sprint7-phase7.2.8): replace with live LLM call when API key is
    available. The wiring is straightforward:

        from campaigns.services.cacheable_preamble import build as build_assembled
        assembled = build_assembled(
            product=prompt_template.product,
            prompt_template=prompt_template,
            prospect=None,
            flagged_count=1,
            include_conversation=False,
        )
        system = '\\n\\n'.join(b.content for b in assembled.system_blocks)
        # Feed `system` + inbound body into anthropic.Anthropic().messages.create
        # with the model from prompt_template.model, return the text blocks.

    Blocked in the current sandbox environment: (a) anthropic SDK is not
    installed in venv, (b) no ANTHROPIC_API_KEY available here. Rather than
    fake scores, Phase 7.2.8 commits the rule-based-on-stub output with
    this TODO and the note in commit 79b.. that the scores reflect stub
    behavior, not real model output. The golden set runs meaningfully once
    the Claude Code runtime provides API access.
    """
    ideal = (pair.get('ideal_reply', {}) or {}).get('body_text')
    return ideal


def run_eval(product_slug: str, mode: str = 'rule_based') -> EvalReport:
    """Run the eval harness for one product. Loads the golden set file,
    iterates pairs, generates (via stub for Phase 7.0), scores, returns
    a structured report."""
    brain = load_brain_by_product(product_slug)
    pt = PromptTemplate.objects.get(
        pk=brain.reply_prompt_template_id,
    ) if brain.reply_prompt_template_id else None

    golden_path = Path(brain.content_strategy.get('__unused_', '')) if False else Path(
        f'tests/golden_sets/{product_slug}.json'
    )
    if not golden_path.exists():
        return EvalReport(
            product_slug=product_slug,
            brain_version=brain.brain_version,
            prompt_template_name=pt.name if pt else '(none)',
            prompt_template_version=pt.version if pt else 0,
            total_pairs=0,
            passed_pairs=0,
            score_pct=0,
            mode=mode,
            results=[PairResult('_missing', 'none', None, None, False, 0,
                                [f'golden set file missing: {golden_path}'])],
        )

    data = json.loads(golden_path.read_text())
    pairs = data.get('pairs', [])

    results: List[PairResult] = []
    for pair in pairs:
        generated = _stub_generate(pair, pt)
        pr = _check_rule_based(pair, brain, pt, generated)
        results.append(pr)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    score = int((passed / total) * 100) if total else 0

    return EvalReport(
        product_slug=product_slug,
        brain_version=brain.brain_version,
        prompt_template_name=pt.name if pt else '(none)',
        prompt_template_version=pt.version if pt else 0,
        total_pairs=total,
        passed_pairs=passed,
        score_pct=score,
        mode=mode,
        results=results,
    )
