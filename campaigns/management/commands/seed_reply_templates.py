"""
Seed auto-reply templates for all campaigns x classifications.

Usage:
    python manage.py seed_reply_templates
    python manage.py seed_reply_templates --force  # overwrite existing

Creates 15 templates: 5 campaigns x 3 classifications (interested, question, other).
Each template uses warm BNI-appropriate language with product-specific copy.
"""
from django.core.management.base import BaseCommand
from campaigns.models import Campaign, ReplyTemplate


SCHEDULING_LINK = 'https://calendar.app.google/fzQ5iQLGHakimfjv7'
SCHEDULING_CTA = (
    '<p>If it\'s easier, you can book a time that suits you here:</p>'
    '<p><a href="' + SCHEDULING_LINK + '">Schedule TaggIQ Demo with Prakash</a></p>'
)
FP_SCHEDULING_CTA = (
    '<p>If it\'s easier, you can book a time that suits you here:</p>'
    '<p><a href="' + SCHEDULING_LINK + '">Schedule a Call with Prakash</a></p>'
)

# Templates keyed by (product, classification)
# Voice: warm, conversational, humble, short. Like a BNI colleague, not a salesperson.
TEMPLATES = {
    # ─── TaggIQ: Interested ─────────────────────────────────────────
    ('taggiq', 'interested'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Great to hear from you! Thanks for the quick reply.</p>

<p>I'd be happy to show you how TaggIQ works. It's designed specifically for promo businesses to keep quotes, orders, artwork approvals and invoicing in one place — so you spend less time on admin and more on customers.</p>

<p>Probably easiest if I walk you through it in a quick 20-minute demo.</p>

{SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    # ─── TaggIQ: Question ───────────────────────────────────────────
    ('taggiq', 'question'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Thanks for the question — happy to help.</p>

<p>TaggIQ is a system built specifically for promotional product businesses. It handles enquiries, quoting, artwork approvals, orders, invoicing and payments — all from one place. It also connects with promo suppliers for easy product sourcing and supports common decoration methods like embroidery, screen printing and DTF.</p>

<p>Probably easiest if I show you how it works rather than trying to explain it all over email.</p>

{SCHEDULING_CTA}

<p>Feel free to reply with any other questions in the meantime.</p>

<p>Best,<br>Prakash</p>""",
    },
    # ─── TaggIQ: Other ──────────────────────────────────────────────
    ('taggiq', 'other'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': """<p>Hi {{FNAME}},</p>

<p>Thanks for getting back to me — I really appreciate you taking the time to reply.</p>

<p>I reached out because I thought TaggIQ might be relevant for {{COMPANY}}. It's a system I built from our own experience running a promo business, after seeing how far behind the tools still are compared to other industries.</p>

<p>If you're ever curious to see what we ended up building, I'd always be happy to show you. No pressure at all.</p>

<p>Wishing you a great week.</p>

<p>Best,<br>Prakash</p>""",
    },

    # ─── Fully Promoted: Interested ─────────────────────────────────
    ('fullypromoted', 'interested'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>That's great to hear — thanks for your interest.</p>

<p>We're expanding the Fully Promoted franchise network in Ireland and looking for the right partners in key locations. As an established business, {{{{COMPANY}}}} could be a really good fit.</p>

<p>I'd love to share more about the opportunity and what it could look like for you.</p>

{FP_SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    # ─── Fully Promoted: Question ───────────────────────────────────
    ('fullypromoted', 'question'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Thanks for the question — happy to explain.</p>

<p>Fully Promoted is a global franchise network specialising in branded merchandise, promotional products and custom apparel. The franchise model provides full training, supplier relationships and marketing support — while you bring the local expertise and customer relationships.</p>

<p>Probably easiest if we jump on a quick call so I can go into more detail.</p>

{FP_SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    # ─── Fully Promoted: Other ──────────────────────────────────────
    ('fullypromoted', 'other'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': """<p>Hi {{FNAME}},</p>

<p>Thanks for getting back to me — I appreciate the reply.</p>

<p>I reached out because {{COMPANY}} caught my eye as a strong business in the {{CITY}} area. We're expanding the Fully Promoted franchise network in Ireland and I thought there might be a natural fit.</p>

<p>Would you be open to a brief conversation? No commitment at all — happy to share more about what the opportunity looks like.</p>

<p>Best,<br>Prakash</p>""",
    },

    # ─── Kritno: Interested ─────────────────────────────────────────
    ('kritno', 'interested'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Great to hear from you! Thanks for the quick reply.</p>

<p>I'd be happy to show you what Kritno can do for {{{{COMPANY}}}}. It's designed to make creative production faster and more efficient for teams like yours.</p>

{FP_SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    # ─── Kritno: Question ───────────────────────────────────────────
    ('kritno', 'question'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Thanks for the question — happy to help.</p>

<p>Kritno is a creative production platform that helps teams manage artwork, proofing and design workflows more efficiently. It's built for businesses like {{{{COMPANY}}}} that handle a lot of creative output.</p>

<p>Probably easiest if I show you how it works rather than explaining over email.</p>

{FP_SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    # ─── Kritno: Other ──────────────────────────────────────────────
    ('kritno', 'other'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': """<p>Hi {{FNAME}},</p>

<p>Thanks for getting back to me — I appreciate the reply.</p>

<p>I thought Kritno might be relevant for {{COMPANY}} given the creative work you do. If you're ever curious to see how it works, I'd be happy to show you. No pressure at all.</p>

<p>Best,<br>Prakash</p>""",
    },
}

# Default templates for 'other' product type
DEFAULT_TEMPLATES = {
    ('other', 'interested'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Great to hear from you! Thanks for the quick reply.</p>

<p>I'd love to share more about how we can help {{{{COMPANY}}}}.</p>

{FP_SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    ('other', 'question'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': f"""<p>Hi {{{{FNAME}}}},</p>

<p>Thanks for the question — happy to help.</p>

<p>Probably easiest if we jump on a quick call so I can explain properly.</p>

{FP_SCHEDULING_CTA}

<p>Best,<br>Prakash</p>""",
    },
    ('other', 'other'): {
        'subject': 'Re: {{ORIGINAL_SUBJECT}}',
        'body': """<p>Hi {{FNAME}},</p>

<p>Thanks for getting back to me — I really appreciate the reply.</p>

<p>Would you be open to a brief chat? No pressure at all — just wanted to make sure you had the chance to see if it's relevant.</p>

<p>Best,<br>Prakash</p>""",
    },
}


class Command(BaseCommand):
    help = 'Seed auto-reply templates for all campaigns (15 templates: 5 campaigns x 3 classifications)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Overwrite existing templates')

    def handle(self, *args, **options):
        force = options['force']
        campaigns = Campaign.objects.all()

        if not campaigns.exists():
            self.stderr.write(self.style.ERROR('No campaigns found. Create campaigns first.'))
            return

        created = 0
        updated = 0
        skipped = 0

        for campaign in campaigns:
            for classification in ('interested', 'question', 'other'):
                # Look up template by product type
                key = (campaign.product, classification)
                template_data = TEMPLATES.get(key) or DEFAULT_TEMPLATES.get(('other', classification))

                if not template_data:
                    self.stderr.write(f'  No template data for {key}')
                    continue

                existing = ReplyTemplate.objects.filter(
                    campaign=campaign, classification=classification,
                ).first()

                if existing and not force:
                    skipped += 1
                    self.stdout.write(f'  SKIP: {campaign.name} / {classification} (already exists)')
                    continue

                if existing and force:
                    existing.subject_template = template_data['subject']
                    existing.body_html_template = template_data['body']
                    existing.is_active = True
                    existing.save()
                    updated += 1
                    self.stdout.write(self.style.WARNING(
                        f'  UPDATE: {campaign.name} / {classification}'
                    ))
                else:
                    ReplyTemplate.objects.create(
                        campaign=campaign,
                        classification=classification,
                        subject_template=template_data['subject'],
                        body_html_template=template_data['body'],
                        is_active=True,
                    )
                    created += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  CREATE: {campaign.name} / {classification}'
                    ))

        self.stdout.write('\n' + '=' * 40)
        self.stdout.write(f'Created: {created}')
        self.stdout.write(f'Updated: {updated}')
        self.stdout.write(f'Skipped: {skipped}')
        self.stdout.write(f'Total campaigns: {campaigns.count()}')
