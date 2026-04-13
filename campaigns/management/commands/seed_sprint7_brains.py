"""Sprint 7 Phase 7.1.6 + 7.1.7 — seed ProductBrain rows for TaggIQ, FP
Franchise, and print-promo.

Idempotent. Re-run safely — existing brains are updated in place (version
bumps when content hash changes), existing PromptTemplate rows for
print-promo are preserved (Lisa v6 is live on EC2).

Run on:
    local:   venv/bin/python manage.py seed_sprint7_brains
    EC2:     docker exec outreach_cron python manage.py seed_sprint7_brains

Each run prints a summary of created/updated rows.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db import transaction

from campaigns.models import Product, ProductBrain, PromptTemplate


# ---------------------------------------------------------------------------
# Brain JSON definitions. These are the platform configuration for each
# product. Edit here + re-run the command to update the DB.
#
# Voice rules (system_prompt) are kept as short platform references. Full
# voice detail lives in the /taggiq-email-expert and /fp-email-expert skill
# files, which handle_replies invokes via the Claude Code CLI — this is
# consistent with the Sprint 5 v5 pattern where voice is in DB and the
# execution recipe is in code (see docs/ai-reply-architecture.md).
# ---------------------------------------------------------------------------

TAGGIQ_VOICE = """You are Prakash Inani, founder of TaggIQ.

Voice rules:
- Conversational, like a text from a colleague. Never corporate marketing.
- Short replies. Under 130 words. No fluff, no filler, no emojis.
- Never use em dashes. Use hyphens with spaces instead.
- Never mention Fully Promoted when talking to Irish shops (conflict of interest).
- For BNI contacts: reference being a fellow BNI member who spent 20 years in software.
- For cold leads: "spent 20 years in software before moving into this industry".
- Offer: 3 months free for BNI, free trial for cold leads.
- Demo link: https://calendar.app.google/fzQ5iQLGHakimfjv7
- Self-trial: https://taggiq.com/signup

Product summary (for accuracy, not repetition):
TaggIQ is the POS platform for print and promo shops. Quote in 3 minutes.
Direct supplier ordering (submit POs to suppliers from inside TaggIQ).
Decoration options pulled per garment from supplier catalogs. Branded
webstores for your customers. Leads, quotes, orders, invoices, payments
in one system.

Hard rules:
- Never quote a price in an email. If asked, offer to discuss on a call.
- Never promise a feature or timeline not already shipped.
- If the reply needs a human judgment call (contract, procurement, legal),
  escalate instead of replying.
"""

FP_FRANCHISE_VOICE = """You are Prakash Inani, master franchise holder for
Fully Promoted Ireland.

Voice rules:
- Warm, professional, confident. Never pushy.
- Fully Promoted is the world's largest promotional products franchise:
  #1 for 25 years, 300+ locations worldwide.
- This is NOT a software pitch. It's a business opportunity conversation.
- First call is a qualification call. Next step after that call is always
  sending the Personal Profile Form (Wufoo link).
- 3-call cadence: intro call -> profile form review -> deep discovery.
- Short replies. Under 130 words. No fluff. No em dashes.
- Never commit to urgent timelines. Standard lead time is 2 weeks.

Hard rules:
- Never discuss franchise fees in email. Always "happy to walk through on a call".
- If the reply involves legal or contractual specifics, escalate.
- If prospect expresses strong interest, next step is Wufoo profile form.
"""


def _upsert_prompt_template(product_slug: str, name: str, system_prompt: str,
                            from_name: str, signature_name: str) -> PromptTemplate:
    """Create or update an active email_reply PromptTemplate for a product."""
    product = Product.objects.get(slug=product_slug)
    existing = PromptTemplate.objects.filter(
        product=product, feature='email_reply', is_active=True,
    ).first()
    if existing:
        # Preserve the print-promo Lisa voice untouched (live on EC2)
        if product_slug == 'print-promo':
            return existing
        # Update TaggIQ / FP Franchise in-place
        if existing.system_prompt.strip() != system_prompt.strip():
            existing.system_prompt = system_prompt
            existing.version = (existing.version or 0) + 1
            existing.save()
        return existing
    return PromptTemplate.objects.create(
        product=product,
        feature='email_reply',
        name=name,
        system_prompt=system_prompt,
        model='claude-sonnet-4-6',
        max_tokens=500,
        temperature=0.7,
        is_active=True,
        version=1,
        from_name=from_name,
        signature_name=signature_name,
        max_reply_words=130,
        warn_reply_words=100,
    )


def taggiq_brain() -> dict:
    return {
        'sequence_rules': {
            'new':         {'next': 'seq1',     'after_hours': 0},
            'contacted':   {'next': 'seq_next', 'after_hours': 168},
            'interested':  {'next': None, 'handoff': 'ai_reply'},
            'engaged':     {'next': None, 'handoff': 'ai_reply'},
        },
        'timing_rules': {
            'min_hours_since_inbound': 24,
            'min_hours_since_email':   48,
            'min_hours_since_call':    48,
            'max_emails_per_week':      3,
            'max_calls_per_prospect':   2,
        },
        'terminal_states': [
            'demo_scheduled', 'design_partner', 'opted_out',
            'not_interested', 'bounce',
        ],
        'escalation_rules': {
            'on_keyword': ['contract', 'legal', 'procurement', 'NDA', 'invoice dispute'],
            'on_status':  ['demo_scheduled'],
            'on_reply_count_gte': 4,
        },
        'success_signals': {
            'primary':   'demo_scheduled',
            'secondary': ['interested', 'engaged', 'design_partner'],
        },
        'call_eligibility': {
            'min_emails_sent':    2,
            'require_phone':      True,
            'skip_if_replied':    True,
            'allowed_countries':  ['US', 'United States', 'IE', 'Ireland', 'GB', 'United Kingdom'],
            'max_calls_per_prospect': 2,
        },
        'content_strategy': {
            'per_sequence': {
                'seq1': 'introduce supplier ordering capability with Loom link',
                'seq2': '3-minute quote proof point (decoration options)',
                'seq3': 'branded webstores + soft breakup',
                'seq4': 'final soft close, "what would it take"',
            },
            'reply_goals': {
                'interested': 'qualify budget + timeline, propose demo',
                'question':   'answer tactically, nudge to a call or demo',
            },
            'call_goals': {
                'warm_reengagement': 'reference the last email specifically, ask for 60 seconds',
            },
        },
        'jobs': {
            'reply':              {'model': 'claude-sonnet-4-6', 'max_tokens': 500, 'cache': True},
            'call_opener':        {'model': 'claude-sonnet-4-6', 'max_tokens': 120},
            'classify':           {'model': 'claude-sonnet-4-6', 'method': 'regex_first'},
            'transcript_insight': {'model': 'claude-sonnet-4-6', 'max_tokens': 1500},
        },
        'golden_set_path': 'tests/golden_sets/taggiq.json',
        'eval_threshold_pct': 90,
    }


def fp_franchise_brain() -> dict:
    d = taggiq_brain()
    d['sequence_rules'] = {
        'new':         {'next': 'seq1',     'after_hours': 0},
        'contacted':   {'next': 'seq_next', 'after_hours': 168},
        'interested':  {'next': None, 'handoff': 'ai_reply'},
        'engaged':     {'next': None, 'handoff': 'ai_reply'},
    }
    d['escalation_rules'] = {
        'on_keyword': ['fee', 'franchise fee', 'contract', 'legal', 'royalty', 'investment'],
        'on_status':  ['interested', 'demo_scheduled'],
        'on_reply_count_gte': 2,
    }
    d['content_strategy'] = {
        'per_sequence': {
            'seq1': 'introduce FP Ireland master franchise, invite first call',
            'seq2': 'credibility stack: #1 promo franchise, 25 years, 300+ locations',
            'seq3': 'local opportunity framing + soft breakup',
            'seq4': 'final ask, "want to have a quick chat"',
        },
        'reply_goals': {
            'interested': 'book first qualification call, no fee details by email',
            'question':   'answer briefly, route to call',
        },
        'call_goals': {
            'warm_reengagement': 'reference their territory and the previous email',
        },
    }
    d['call_eligibility']['allowed_countries'] = ['IE', 'Ireland']
    d['success_signals'] = {
        'primary':   'demo_scheduled',
        'secondary': ['interested', 'engaged'],
    }
    d['golden_set_path'] = 'tests/golden_sets/fullypromoted.json'
    return d


def print_promo_brain() -> dict:
    """Lisa's brain for FP Kingswood + Dublin Construction campaigns on EC2."""
    d = taggiq_brain()
    d['sequence_rules'] = {
        'new':         {'next': 'seq1',     'after_hours': 0},
        'contacted':   {'next': 'seq_next', 'after_hours': 168},
        'interested':  {'next': None, 'handoff': 'ai_reply'},
        'engaged':     {'next': None, 'handoff': 'ai_reply'},
    }
    d['escalation_rules'] = {
        'on_keyword': ['contract', 'legal', 'procurement', 'tender'],
        'on_status':  ['demo_scheduled'],
        'on_reply_count_gte': 4,
    }
    d['content_strategy'] = {
        'per_sequence': {
            'seq1': 'hello neighbour, we do branded workwear/hi-vis/van signage for trades',
            'seq2': 'proof points: quick turnarounds, samples delivered locally',
            'seq3': 'soft breakup, offer of samples',
        },
        'reply_goals': {
            'interested': 'gather details (logo, quantities, timelines), route to quote',
            'question':   'answer tactically, offer sample drop-off',
        },
        'call_goals': {
            'warm_reengagement': 'reference their van or crew specifically',
        },
    }
    d['call_eligibility']['allowed_countries'] = ['IE', 'Ireland']
    d['golden_set_path'] = 'tests/golden_sets/print-promo.json'
    return d


BRAIN_CONFIGS = {
    'taggiq':         (taggiq_brain,         TAGGIQ_VOICE,        'Prakash Inani',  'Prakash'),
    'fullypromoted':  (fp_franchise_brain,   FP_FRANCHISE_VOICE,  'Prakash Inani',  'Prakash'),
    'print-promo':    (print_promo_brain,    None,                '',               ''),
}


class Command(BaseCommand):
    help = 'Sprint 7 — seed ProductBrain rows for TaggIQ, FP Franchise, and print-promo'

    def add_arguments(self, parser):
        parser.add_argument('--product', help='Only seed one product (slug). Default: all.')
        parser.add_argument('--dry-run', action='store_true', help='Print what would change, do not write.')

    def handle(self, *args, **opts):
        only = opts.get('product')
        dry = opts.get('dry_run', False)

        created, updated, skipped = [], [], []

        for slug, (build_fn, voice, from_name, signature) in BRAIN_CONFIGS.items():
            if only and slug != only:
                continue
            try:
                product = Product.objects.get(slug=slug)
            except Product.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'- {slug}: product missing, skipping'))
                continue

            # 1. Voice row
            if voice:
                if dry:
                    self.stdout.write(f'- {slug}: would upsert PromptTemplate')
                    pt = None
                else:
                    pt = _upsert_prompt_template(
                        slug,
                        name=f'{slug} email reply v1 (Sprint 7)',
                        system_prompt=voice,
                        from_name=from_name,
                        signature_name=signature,
                    )
            else:
                # print-promo: keep the live Lisa voice untouched
                from campaigns.models import PromptTemplate as PT
                pt = PT.objects.filter(product=product, feature='email_reply', is_active=True).first()

            # 2. Brain row
            cfg = build_fn()
            existing = ProductBrain.objects.filter(product=product).first()
            if existing:
                if dry:
                    self.stdout.write(f'- {slug}: would update ProductBrain v{existing.version}')
                    updated.append(slug)
                    continue
                with transaction.atomic():
                    for k, v in cfg.items():
                        setattr(existing, k, v)
                    if pt:
                        existing.reply_prompt_template = pt
                    existing.version += 1
                    existing.is_active = True
                    existing.save()
                updated.append(f'{slug} -> v{existing.version}')
            else:
                if dry:
                    self.stdout.write(f'- {slug}: would create ProductBrain v1')
                    created.append(slug)
                    continue
                with transaction.atomic():
                    pb = ProductBrain.objects.create(
                        product=product,
                        version=1,
                        is_active=True,
                        reply_prompt_template=pt,
                        **cfg,
                    )
                created.append(f'{slug} -> v{pb.version}')

        self.stdout.write(self.style.SUCCESS('=== Sprint 7 brain seed ==='))
        if created:
            self.stdout.write(f'Created: {", ".join(created)}')
        if updated:
            self.stdout.write(f'Updated: {", ".join(updated)}')
        if not (created or updated):
            self.stdout.write('No changes.')
