"""Sprint 7 — brain loader.

Loads a per-prospect Brain object by walking:
    prospect -> campaign -> product -> ProductBrain
               \-> CampaignBrainOverride (optional, sparse)

Returns a frozen dataclass that the rules_engine + next_action services
consume. ONLY place in the codebase that reads ProductBrain rows — any
command that needs brain config goes through load_brain().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from campaigns.models import (
    Campaign,
    CampaignBrainOverride,
    ProductBrain,
    Prospect,
)


@dataclass(frozen=True)
class Brain:
    """Merged view of ProductBrain + optional CampaignBrainOverride."""

    product_slug: str
    brain_version: int
    sequence_rules: Dict[str, Any]
    timing_rules: Dict[str, Any]
    terminal_states: List[str]
    escalation_rules: Dict[str, Any]
    success_signals: Dict[str, Any]
    call_eligibility: Dict[str, Any]
    content_strategy: Dict[str, Any]
    jobs: Dict[str, Any]
    reply_prompt_template_id: Optional[int] = None
    call_script_default_id: Optional[int] = None
    campaign_id: Optional[str] = None
    override_keys: List[str] = field(default_factory=list)

    def job(self, name: str) -> Dict[str, Any]:
        """Return the per-job config for `name` with sane defaults.

        Sonnet 4.6 is the floor model (Prakash 2026-04-13). Any job not
        listed in the brain's `jobs` dict gets defaulted here so the
        executors never crash on a missing key.
        """
        defaults = {
            'reply':              {'model': 'claude-sonnet-4-6', 'max_tokens': 500, 'cache': True},
            'call_opener':        {'model': 'claude-sonnet-4-6', 'max_tokens': 120, 'cache': False},
            'classify':           {'model': 'claude-sonnet-4-6', 'method': 'regex_first'},
            'transcript_insight': {'model': 'claude-sonnet-4-6', 'max_tokens': 1500, 'cache': False},
        }
        base = defaults.get(name, {'model': 'claude-sonnet-4-6'})
        return {**base, **self.jobs.get(name, {})}

    def is_terminal(self, status: str) -> bool:
        return status in (self.terminal_states or [])


class BrainNotFound(Exception):
    """Raised when a Product has no ProductBrain row yet."""


def load_brain(prospect: Prospect) -> Brain:
    """Load + merge the brain for this prospect.

    Raises BrainNotFound if the product has no brain row. Callers must
    handle this — the flag=False code path never calls load_brain(), so
    in the live pipeline this only fires when use_context_assembler=True
    on a campaign whose product is not yet configured, which is a setup
    error worth failing loudly on.
    """
    campaign: Campaign = prospect.campaign
    if campaign is None or campaign.product_ref_id is None:
        raise BrainNotFound(
            f'Prospect {prospect.id} has no campaign.product_ref — cannot load brain',
        )
    try:
        pb: ProductBrain = ProductBrain.objects.select_related(
            'reply_prompt_template', 'call_script_default',
        ).get(product_id=campaign.product_ref_id, is_active=True)
    except ProductBrain.DoesNotExist:
        raise BrainNotFound(
            f'No active ProductBrain for product={campaign.product_ref.slug}',
        )

    override = CampaignBrainOverride.objects.filter(campaign=campaign).first()
    overrides = dict(override.overrides) if override else {}

    def merged(key: str, default):
        base = getattr(pb, key)
        if key in overrides:
            if isinstance(base, dict) and isinstance(overrides[key], dict):
                # Shallow-merge dicts so overrides only replace the keys they specify
                return {**base, **overrides[key]}
            return overrides[key]
        return base

    return Brain(
        product_slug=campaign.product_ref.slug,
        brain_version=pb.version,
        sequence_rules=merged('sequence_rules', {}),
        timing_rules=merged('timing_rules', {}),
        terminal_states=merged('terminal_states', []),
        escalation_rules=merged('escalation_rules', {}),
        success_signals=merged('success_signals', {}),
        call_eligibility=merged('call_eligibility', {}),
        content_strategy=merged('content_strategy', {}),
        jobs=merged('jobs', {}),
        reply_prompt_template_id=pb.reply_prompt_template_id,
        call_script_default_id=pb.call_script_default_id,
        campaign_id=str(campaign.id),
        override_keys=sorted(overrides.keys()),
    )


def load_brain_by_product(product_slug: str) -> Brain:
    """Load a brain without a prospect — used by eval harness + brain_doctor."""
    pb = ProductBrain.objects.select_related(
        'product', 'reply_prompt_template', 'call_script_default',
    ).get(product__slug=product_slug, is_active=True)
    return Brain(
        product_slug=pb.product.slug,
        brain_version=pb.version,
        sequence_rules=dict(pb.sequence_rules or {}),
        timing_rules=dict(pb.timing_rules or {}),
        terminal_states=list(pb.terminal_states or []),
        escalation_rules=dict(pb.escalation_rules or {}),
        success_signals=dict(pb.success_signals or {}),
        call_eligibility=dict(pb.call_eligibility or {}),
        content_strategy=dict(pb.content_strategy or {}),
        jobs=dict(pb.jobs or {}),
        reply_prompt_template_id=pb.reply_prompt_template_id,
        call_script_default_id=pb.call_script_default_id,
    )
