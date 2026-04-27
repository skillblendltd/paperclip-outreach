"""
Seed the Kritno Ireland - Web Agencies campaign with 5x2 email templates.
Run on EC2: python manage.py seed_kritno_campaign
"""

from django.core.management.base import BaseCommand
from campaigns.models import Product, Campaign, EmailTemplate


TEMPLATES = [
    # Sequence 1 - EAA Wake-Up Call
    {
        "seq": 1, "var": "A",
        "name": "kritno_web_agencies_seq1_a",
        "label": "EAA Wake-Up Call",
        "subject": "Quick question about your clients' websites",
        "body": """<p>Hi {{FNAME}},</p>

<p>I run Kritno - an accessibility scanning platform built for agencies like {{COMPANY}}.</p>

<p>Since the EU Accessibility Act kicked in, every client website you manage needs to meet WCAG 2.1 Level AA standards. Most don't - 96% of websites still fail basic accessibility checks.</p>

<p>We built a tool that scans sites for accessibility issues and generates ready-to-paste code fixes. Signup is free - you can scan your first site in about 60 seconds.</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Cheers,<br>Prakash<br>Kritno | kritno.com</p>""",
    },
    {
        "seq": 1, "var": "B",
        "name": "kritno_web_agencies_seq1_b",
        "label": "EAA Wake-Up Call",
        "subject": "The EAA deadline passed - are your clients covered?",
        "body": """<p>Hi {{FNAME}},</p>

<p>I run Kritno - an accessibility scanning platform built for agencies like {{COMPANY}}.</p>

<p>Since the EU Accessibility Act kicked in, every client website you manage needs to meet WCAG 2.1 Level AA standards. Most don't - 96% of websites still fail basic accessibility checks.</p>

<p>We built a tool that scans sites for accessibility issues and generates ready-to-paste code fixes. Signup is free - you can scan your first site in about 60 seconds.</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Cheers,<br>Prakash<br>Kritno | kritno.com</p>""",
    },
    # Sequence 2 - The Proof
    {
        "seq": 2, "var": "A",
        "name": "kritno_web_agencies_seq2_a",
        "label": "The Proof",
        "subject": "Most Irish agency sites fail this test",
        "body": """<p>Hi {{FNAME}},</p>

<p>Following up on my note last week. We scanned a sample of Irish agency websites recently - nearly all had WCAG 2.1 AA violations that could now trigger complaints under the EAA.</p>

<p>The common ones: missing alt text, poor colour contrast, broken keyboard navigation. Easy to miss, easy to fix once you know where they are.</p>

<p>Kritno flags exactly what's wrong and gives you the code to fix it - specific to your framework (React, Vue, Angular, whatever the site uses).</p>

<p>Free to sign up, takes a minute:</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Prakash</p>""",
    },
    {
        "seq": 2, "var": "B",
        "name": "kritno_web_agencies_seq2_b",
        "label": "The Proof",
        "subject": "96% of websites have accessibility issues",
        "body": """<p>Hi {{FNAME}},</p>

<p>Following up on my note last week. We scanned a sample of Irish agency websites recently - nearly all had WCAG 2.1 AA violations that could now trigger complaints under the EAA.</p>

<p>The common ones: missing alt text, poor colour contrast, broken keyboard navigation. Easy to miss, easy to fix once you know where they are.</p>

<p>Kritno flags exactly what's wrong and gives you the code to fix it - specific to your framework (React, Vue, Angular, whatever the site uses).</p>

<p>Free to sign up, takes a minute:</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Prakash</p>""",
    },
    # Sequence 3 - Partnership Offer
    {
        "seq": 3, "var": "A",
        "name": "kritno_web_agencies_seq3_a",
        "label": "Partnership Offer",
        "subject": "Free Kritno access for {{COMPANY}}",
        "body": """<p>Hi {{FNAME}},</p>

<p>One more thought. We're selecting a small group of Irish web agencies for our founding partner programme - full platform access at no cost.</p>

<p>The idea: agencies like yours manage dozens of client websites. If Kritno helps you deliver WCAG 2.1 AA compliance as part of your service offering, that's a new revenue stream for you and better coverage for your clients.</p>

<p>What you'd get:</p>
<ul>
<li>Unlimited scanning across client sites</li>
<li>AI-generated code fixes per issue</li>
<li>Compliance reports you can share with clients</li>
<li>Priority support from our team</li>
</ul>

<p>No cost, no commitment. Sign up here and I'll upgrade your account:</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Prakash<br>kritno.com</p>""",
    },
    {
        "seq": 3, "var": "B",
        "name": "kritno_web_agencies_seq3_b",
        "label": "Partnership Offer",
        "subject": "Selecting agencies for our founding partner programme",
        "body": """<p>Hi {{FNAME}},</p>

<p>One more thought. We're selecting a small group of Irish web agencies for our founding partner programme - full platform access at no cost.</p>

<p>The idea: agencies like yours manage dozens of client websites. If Kritno helps you deliver WCAG 2.1 AA compliance as part of your service offering, that's a new revenue stream for you and better coverage for your clients.</p>

<p>What you'd get:</p>
<ul>
<li>Unlimited scanning across client sites</li>
<li>AI-generated code fixes per issue</li>
<li>Compliance reports you can share with clients</li>
<li>Priority support from our team</li>
</ul>

<p>No cost, no commitment. Sign up here and I'll upgrade your account:</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Prakash<br>kritno.com</p>""",
    },
    # Sequence 4 - Client Angle
    {
        "seq": 4, "var": "A",
        "name": "kritno_web_agencies_seq4_a",
        "label": "Client Angle",
        "subject": "Your clients might start asking about this",
        "body": """<p>Hi {{FNAME}},</p>

<p>Quick thought - more Irish businesses are getting accessibility complaints since EAA enforcement started. When that happens, the first call goes to their web agency.</p>

<p>A few agencies we work with now include a WCAG 2.1 AA audit as part of their standard delivery. Takes 5 minutes with Kritno, and it's becoming a genuine differentiator in pitches.</p>

<p>Free to sign up - happy to upgrade you to our founding partner tier if you want to try it on a current project. Just reply and I'll sort it.</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Prakash</p>""",
    },
    {
        "seq": 4, "var": "B",
        "name": "kritno_web_agencies_seq4_b",
        "label": "Client Angle",
        "subject": "Accessibility is becoming a client expectation",
        "body": """<p>Hi {{FNAME}},</p>

<p>Quick thought - more Irish businesses are getting accessibility complaints since EAA enforcement started. When that happens, the first call goes to their web agency.</p>

<p>A few agencies we work with now include a WCAG 2.1 AA audit as part of their standard delivery. Takes 5 minutes with Kritno, and it's becoming a genuine differentiator in pitches.</p>

<p>Free to sign up - happy to upgrade you to our founding partner tier if you want to try it on a current project. Just reply and I'll sort it.</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>Prakash</p>""",
    },
    # Sequence 5 - Gentle Close
    {
        "seq": 5, "var": "A",
        "name": "kritno_web_agencies_seq5_a",
        "label": "Gentle Close",
        "subject": "Last note from me",
        "body": """<p>Hi {{FNAME}},</p>

<p>Last note on this - I know inboxes are busy.</p>

<p>If accessibility compliance isn't on your radar right now, no worries at all. But if it comes up with a client down the line, the founding partner offer stands - free signup, full access.</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>All the best with {{COMPANY}}.</p>

<p>Prakash</p>""",
    },
    {
        "seq": 5, "var": "B",
        "name": "kritno_web_agencies_seq5_b",
        "label": "Gentle Close",
        "subject": "Closing the loop",
        "body": """<p>Hi {{FNAME}},</p>

<p>Last note on this - I know inboxes are busy.</p>

<p>If accessibility compliance isn't on your radar right now, no worries at all. But if it comes up with a client down the line, the founding partner offer stands - free signup, full access.</p>

<p><a href="https://kritno.com/register">https://kritno.com/register</a></p>

<p>All the best with {{COMPANY}}.</p>

<p>Prakash</p>""",
    },
]


class Command(BaseCommand):
    help = "Seed the Kritno Ireland - Web Agencies campaign and email templates"

    def handle(self, *args, **options):
        product = Product.objects.get(slug="kritno")

        campaign, created = Campaign.objects.get_or_create(
            name="Kritno Ireland - Web Agencies",
            defaults={
                "product": "kritno",
                "product_ref": product,
                "from_name": "Prakash from Kritno",
                "from_email": "prakash@kritno.com",
                "reply_to_email": "prakash@kritno.com",
                "sending_enabled": False,
                "max_emails_per_day": 15,
                "min_gap_minutes": 15,
                "max_emails_per_prospect": 5,
                "require_sequence_order": True,
                "follow_up_days": 5,
                "send_window_timezone": "Europe/Dublin",
                "send_window_start_hour": 10,
                "send_window_end_hour": 16,
                "send_window_days": "0,1,2,3,4",
                "auto_reply_enabled": False,
                "batch_size": 100,
                "inter_send_delay_min": 10,
                "inter_send_delay_max": 45,
            },
        )
        status = "CREATED" if created else "EXISTS"
        self.stdout.write(f"Campaign: {campaign.name} ({campaign.id}) - {status}")

        created_count = 0
        for t in TEMPLATES:
            obj, was_created = EmailTemplate.objects.get_or_create(
                campaign=campaign,
                sequence_number=t["seq"],
                ab_variant=t["var"],
                defaults={
                    "template_name": t["name"],
                    "sequence_label": t["label"],
                    "subject_template": t["subject"],
                    "body_html_template": t["body"],
                    "is_active": True,
                },
            )
            if was_created:
                created_count += 1
                self.stdout.write(f"  Created: Seq {t['seq']}{t['var']} - {t['label']}")
            else:
                self.stdout.write(f"  Exists:  Seq {t['seq']}{t['var']}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! {created_count} templates created. Campaign ID: {campaign.id}"
        ))
        self.stdout.write(
            "\nNext steps:"
            "\n  1. Verify prakash@kritno.com email is set up"
            "\n  2. Import prospects: python import_prospects.py --campaign-id <ID> --csv output/kritno_ireland_clean.csv"
            "\n  3. Set sending_enabled=True when ready to launch"
        )
