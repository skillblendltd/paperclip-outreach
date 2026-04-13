"""Shadow eval for flat-template vs context-assembled prompts.

Generates BOTH versions of what Claude would see for N real prospects and
prints them side-by-side for human scoring. Does NOT call Claude, does NOT
send emails, does NOT write to the DB. Purely a read + assemble operation.

Used BEFORE flipping Campaign.use_context_assembler=True to answer the
question: "does context assembly actually improve the prompt Claude will
see, or is it noise?"

Usage:
    python manage.py eval_replies --product taggiq --sample 3
    python manage.py eval_replies --product print-promo --sample 5 --flagged-only

The output shows Block 0 (cacheable prefix, same for both modes), then for
each sampled prospect:
  - Flat mode prompt (what handle_replies would send today)
  - Assembled mode prompt (what handle_replies would send after Phase 2B)
  - Diff summary (size, new sections added, <untrusted> count)

Human reviewer reads the paired prompts and decides if the assembled version
is materially better. If 3-5 reviews say yes, Phase 2B gets unblocked.
"""
import random

from django.core.management.base import BaseCommand, CommandError

from campaigns.models import Product, Prospect, PromptTemplate, InboundEmail
from campaigns.services.cacheable_preamble import build as build_assembled
from campaigns.services.conversation import get_conversation_state


class Command(BaseCommand):
    help = 'Shadow eval: print flat vs context-assembled prompts side-by-side for human scoring'

    def add_arguments(self, parser):
        parser.add_argument(
            '--product', required=True,
            help='Product slug (e.g. taggiq, print-promo, fullypromoted)',
        )
        parser.add_argument(
            '--sample', type=int, default=3,
            help='How many prospects to sample (default 3)',
        )
        parser.add_argument(
            '--flagged-only', action='store_true',
            help='Only sample prospects with a flagged InboundEmail (realistic reply scenario)',
        )
        parser.add_argument(
            '--email', help='Evaluate one specific prospect by email',
        )

    def handle(self, *args, **options):
        slug = options['product']
        sample_size = options['sample']
        flagged_only = options['flagged_only']
        one_email = options.get('email')

        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            raise CommandError(f'Product slug "{slug}" not found')

        pt = PromptTemplate.objects.filter(
            product=product, feature='email_reply', is_active=True,
        ).order_by('-version').first()
        if not pt:
            raise CommandError(f'No active email_reply PromptTemplate for product {slug}')

        self.stdout.write(self.style.SUCCESS(f'=== Shadow eval: {product.name} ==='))
        self.stdout.write(f'Prompt: {pt.name} (v{pt.version})')
        self.stdout.write(f'Persona: {pt.from_name} / signature={pt.signature_name}')
        self.stdout.write('')

        # ---------- sample prospects ----------
        prospects = self._sample_prospects(product, sample_size, flagged_only, one_email)
        if not prospects:
            self.stdout.write(self.style.WARNING('No prospects matched the sampling criteria.'))
            return

        self.stdout.write(f'Sampled {len(prospects)} prospect(s):')
        for p in prospects:
            state = get_conversation_state(p)
            self.stdout.write(
                f'  - {p.decision_maker_name or "?"} ({p.business_name or "?"}) '
                f'| status={p.status} | out={state.total_outbound_touches} '
                f'in={state.total_inbound_replies}'
            )
        self.stdout.write('')

        # ---------- for each prospect, assemble both versions ----------
        for i, prospect in enumerate(prospects, 1):
            self.stdout.write('=' * 78)
            self.stdout.write(
                self.style.SUCCESS(
                    f'PROSPECT {i}/{len(prospects)}: '
                    f'{prospect.decision_maker_name} ({prospect.business_name})'
                )
            )
            self.stdout.write('=' * 78)
            self._eval_one(product, pt, prospect)
            self.stdout.write('')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('DONE. Review each pair and score which is better.'))
        self.stdout.write(
            'If 3-5 pairs consistently show assembled > flat, Phase 2B is unblocked — '
            'flip Campaign.use_context_assembler=True on the target campaign.'
        )

    def _sample_prospects(self, product, sample_size, flagged_only, one_email):
        if one_email:
            p = Prospect.objects.filter(email__iexact=one_email).first()
            return [p] if p else []

        if flagged_only:
            inbound_prospects = InboundEmail.objects.filter(
                campaign__product_ref=product,
                needs_reply=True,
                replied=False,
            ).values_list('prospect_id', flat=True).distinct()
            qs = Prospect.objects.filter(id__in=inbound_prospects)
        else:
            qs = Prospect.objects.filter(campaign__product_ref=product).exclude(
                status__in=['not_interested', 'opted_out'],
            )

        all_ids = list(qs.values_list('id', flat=True))
        if not all_ids:
            return []
        random.seed(42)  # deterministic sampling for reproducible eval runs
        picked = random.sample(all_ids, min(sample_size, len(all_ids)))
        return list(Prospect.objects.filter(id__in=picked))

    def _eval_one(self, product, prompt_template, prospect):
        # FLAT mode: what live code does today — voice rules only, no context
        flat_system = prompt_template.system_prompt
        flat_chars = len(flat_system)

        # ASSEMBLED mode: what Phase 2B would send
        assembled = build_assembled(
            product=product,
            prompt_template=prompt_template,
            prospect=prospect,
            flagged_count=1,
            include_conversation=True,
        )
        assembled_chars = assembled.total_char_estimate

        # ---------- print diff summary ----------
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('--- FLAT MODE (what live code sends today) ---'))
        self.stdout.write(f'System prompt size: {flat_chars} chars (~{flat_chars // 4} tokens)')
        self.stdout.write(f'Has conversation context: NO')
        self.stdout.write(f'First 600 chars:\n{flat_system[:600]}')
        self.stdout.write('...' if flat_chars > 600 else '')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('--- ASSEMBLED MODE (what Phase 2B would send) ---'))
        self.stdout.write(f'Total size: {assembled_chars} chars (~{assembled_chars // 4} tokens)')
        self.stdout.write(f'Blocks: {len(assembled.system_blocks)} '
                          f'(cached={sum(1 for b in assembled.system_blocks if b.cache)})')
        # Show only the conversation context block since the preamble+voice is
        # deterministic and the same per prompt template version.
        context_block = next(
            (b for b in assembled.system_blocks if 'prospect_history' in b.content),
            None,
        )
        if context_block:
            self.stdout.write(f'Context window size: {len(context_block.content)} chars')
            self.stdout.write(f'Untrusted tag count: {context_block.content.count("<untrusted>")}')
            self.stdout.write('Context content:')
            self.stdout.write(context_block.content[:2000])
            if len(context_block.content) > 2000:
                self.stdout.write(f'... (+{len(context_block.content) - 2000} more chars)')
        else:
            self.stdout.write(self.style.WARNING('No context block — prospect has no timeline history'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('--- DIFF ---'))
        added = assembled_chars - flat_chars
        self.stdout.write(f'Assembled adds {added} chars vs flat ({added // 4} tokens)')
        self.stdout.write(
            'HUMAN SCORE: does the assembled version give Claude materially better '
            'information? [yes / no / marginal]'
        )
