"""
Seed EmailTemplate records from the hardcoded templates in sender scripts.
One-time migration to move templates into DB.

Usage:
    python manage.py seed_templates           # Seed all campaigns
    python manage.py seed_templates --campaign "TaggIQ BNI"  # Seed one campaign
    python manage.py seed_templates --dry-run # Preview without creating
"""
from django.core.management.base import BaseCommand
from campaigns.models import Campaign, EmailTemplate

# Template data structure:
# { campaign_name_substring: { seq_num: { 'A': {subject, template_name}, 'B': {subject, template_name}, 'body': html, 'label': str } } }

# ── BNI BASE (TaggIQ BNI + Promo Global) ────────────────────────────────

BNI_BASE = {
    1: {
        'label': 'Peer Story',
        'A': {'subject': 'quick question about {{COMPANY}}', 'template_name': 'bni_v2_seq1_a'},
        'B': {'subject': '{{FNAME}}, how do you handle artwork approvals?', 'template_name': 'bni_v2_seq1_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>Spotted you on BNI Connect, looks like we\'re both in the print and promo world.</p>\n<p>Quick question: how does your team handle artwork approvals? I\'ve talked to a bunch of BNI members recently and it\'s wild how many are still chasing approvals over email and WhatsApp.</p>\n<p>Curious if you\'ve found something that works or if it\'s still a pain.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    2: {
        'label': 'Shared Pain',
        'A': {'subject': 'the artwork approval problem', 'template_name': 'bni_v2_seq2_a'},
        'B': {'subject': '{{FNAME}}, thought you\'d find this interesting', 'template_name': 'bni_v2_seq2_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>Thought you might find this interesting. I asked about 20 BNI members in print and promo how they handle artwork approvals and order tracking. Almost everyone said some version of "email back and forth until someone finally says yes."</p>\n<p>I actually built a tool to fix this for my own shop in Dublin. It\'s called <a href="https://taggiq.com/">TaggIQ</a> and it connects quotes, approvals, orders and invoicing in one place. Happy to share what I learned if you\'re dealing with the same thing.</p>\n<p>Either way, no worries.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    3: {
        'label': 'Design Partner',
        'A': {'subject': 'would you want input on this?', 'template_name': 'bni_v2_seq3_a'},
        'B': {'subject': 'looking for 5 BNI members to help shape this', 'template_name': 'bni_v2_seq3_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>So I built <a href="https://taggiq.com/">TaggIQ</a> because I got tired of juggling separate tools for quoting, approvals, orders, and invoicing. Now a customer picks a product, approves the artwork in one click, and the job flows straight through to invoice and payment. One system, nothing re-keyed.</p>\n<p>I\'m looking for a few BNI members to try it and tell me what they think. 3 months free, no commitment, no card required.</p>\n<p>Worth a 15-min chat?</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    4: {
        'label': 'Social Proof',
        'A': {'subject': 'from 4 tools to 1 screen', 'template_name': 'bni_v2_seq4_a'},
        'B': {'subject': '{{FNAME}}, quick update from BNI print shops', 'template_name': 'bni_v2_seq4_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>Quick update. A few BNI print shops started using <a href="https://taggiq.com/">TaggIQ</a> recently.</p>\n<p>One told me they went from spending 30 minutes per quote to 5, because the quote turns into the order turns into the invoice automatically. Another said artwork approvals that took days over email now close in hours with one-click proofing.</p>\n<p>If you\'re ever curious, happy to show you in 15 minutes. No pitch, just a walkthrough.</p>\n<p>Either way, always great being connected through BNI.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    5: {
        'label': 'Breakup',
        'A': {'subject': 'should I stop reaching out?', 'template_name': 'bni_v2_seq5_a'},
        'B': {'subject': '{{FNAME}}, one last one', 'template_name': 'bni_v2_seq5_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>I know how busy things get running a shop, so I\'ll keep this short.</p>\n<p>Is streamlining your workflow something you\'d want to explore, or would you prefer I stop reaching out? Either way is completely fine.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
}

# ── BNI EMBROIDERY OVERRIDES (Seq 1-4 differ, Seq 5 same as base) ───────

BNI_EMBROIDERY = {
    1: {
        'label': 'Peer Story (Embroidery)',
        'A': {'subject': 'quick question about {{COMPANY}}', 'template_name': 'bni_emb_v2_seq1_a'},
        'B': {'subject': '{{FNAME}}, how do you collect sizes for big orders?', 'template_name': 'bni_emb_v2_seq1_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>Spotted you on BNI Connect, looks like we\'re both in the decorated apparel world.</p>\n<p>Quick question: how does your team collect sizes when a customer orders uniforms for 30-40 staff? I\'ve talked to a bunch of BNI members recently and most are still chasing sizes across emails, WhatsApp and spreadsheets.</p>\n<p>Curious if you\'ve found something that works or if it\'s still a headache.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    2: {
        'label': 'Shared Pain (Embroidery)',
        'A': {'subject': 'the size collection problem', 'template_name': 'bni_emb_v2_seq2_a'},
        'B': {'subject': '{{FNAME}}, thought you\'d find this interesting', 'template_name': 'bni_emb_v2_seq2_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>Thought you might find this interesting. I asked about 20 BNI members in embroidery and decorated apparel how they handle size collection and artwork approvals. Almost everyone said some version of "chase them over email for days."</p>\n<p>I actually built a tool to fix this for my own shop in Dublin. It handles quotes, size collection, artwork approvals, orders and invoicing in one place. Happy to share what I learned if you\'re dealing with the same thing.</p>\n<p>Either way, no worries.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    3: {
        'label': 'Design Partner (Embroidery)',
        'A': {'subject': 'would you want input on this?', 'template_name': 'bni_emb_v2_seq3_a'},
        'B': {'subject': 'looking for 5 BNI members to help shape this', 'template_name': 'bni_emb_v2_seq3_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>So I built <a href="https://taggiq.com/">TaggIQ</a> because I got tired of the size collection and approval runaround. Now your customer gets a link, picks their sizes, approves the artwork in one click, and the job flows straight through to invoicing and payment. One system, nothing chased over email.</p>\n<p>I\'m looking for a few BNI members to try it and tell me what they think. 3 months free, no commitment, no card required.</p>\n<p>Worth a 15-min chat?</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    4: {
        'label': 'Social Proof (Embroidery)',
        'A': {'subject': 'from chasing sizes to one link', 'template_name': 'bni_emb_v2_seq4_a'},
        'B': {'subject': '{{FNAME}}, quick update from BNI apparel shops', 'template_name': 'bni_emb_v2_seq4_b'},
        'body': '<p>Hi {{FNAME}},</p>\n<p>Quick update. A few embroidery shops in BNI started using <a href="https://taggiq.com/">TaggIQ</a> recently.</p>\n<p>One told me size collection that used to take days of chasing 40 people over email now happens through a single link. Another said their quote-to-invoice time dropped from hours to minutes because everything flows automatically.</p>\n<p>If you\'re ever curious, happy to show you in 15 minutes. No pitch, just a walkthrough.</p>\n<p>Either way, always great being connected through BNI.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com/">TaggIQ</a></p>',
    },
    5: BNI_BASE[5],  # Same breakup as base
}

# ── IRELAND / LONDON COLD TEMPLATES ──────────────────────────────────────

SIGNS_TEMPLATES = {
    1: {
        'label': 'Cold Open (Signs)',
        'A': {'subject': 'quick question about {{COMPANY}}', 'template_name': '{prefix}_signs_seq1_a'},
        'B': {'subject': 'a question for the team at {{COMPANY}}', 'template_name': '{prefix}_signs_seq1_b'},
        'body': '<p>Hi there,</p>\n<p>I spent 20 years in software before moving into print and signage, and one thing that struck me was how manual the approval process still is.</p>\n<p>Quick question: how does your team handle design approvals before a job goes to production? For vehicle wraps and bespoke installs especially, a missed detail at approval stage can be expensive to fix.</p>\n<p>Curious how you manage it.</p>\n<p>If this isn\'t something you handle, feel free to pass it along to whoever looks after production workflow.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com">TaggIQ</a><br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    2: {
        'label': 'Pain Point (Signs)',
        'A': {'subject': 'the approval problem in signage', 'template_name': '{prefix}_signs_seq2_a'},
        'B': {'subject': '{{FNAME}}, thought this might be relevant', 'template_name': '{prefix}_signs_seq2_b'},
        'body': '<p>Hi there,</p>\n<p>I\'ve been talking with sign shop owners across Ireland about how they handle design approvals and job tracking. Most describe some version of chasing clients over email or WhatsApp until they finally say yes.</p>\n<p>I built a tool to fix this. It\'s called <a href="https://taggiq.com">TaggIQ</a> and it keeps quotes, artwork approvals, orders and invoicing in one place.</p>\n<p>Happy to share more if you\'re dealing with the same thing.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com">TaggIQ</a><br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    3: {
        'label': 'Why TaggIQ (Signs)',
        'A': {'subject': 'why I built TaggIQ', 'template_name': '{prefix}_signs_seq3_a'},
        'B': {'subject': 'a different approach to running a sign shop', 'template_name': '{prefix}_signs_seq3_b'},
        'body': '<p>Hi there,</p>\n<p>I spent 20 years in software before getting into signage, and honestly the tools available didn\'t match how shops actually work.</p>\n<p>So I built TaggIQ. A customer requests a quote, you send it, they approve the design in one click, the job flows straight through to invoicing and payment. No re-keying, no chasing approvals over email, no separate systems.</p>\n<p>If you\'re curious, I\'d love to offer you a free trial. No commitment, no card required.</p>\n<p>You can sign up at <a href="https://taggiq.com/signup">taggiq.com</a> or book a quick 15-minute walkthrough:</p>\n<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    4: {
        'label': 'Cost of Email Approvals (Signs)',
        'A': {'subject': 'the real cost of approving artwork over email', 'template_name': '{prefix}_signs_seq4_a'},
        'B': {'subject': 'one thing most sign shops get wrong', 'template_name': '{prefix}_signs_seq4_b'},
        'body': '<p>Hi there,</p>\n<p>When a customer approves the wrong version because it was buried in an email thread, that reprint is on you.</p>\n<p><a href="https://taggiq.com">TaggIQ</a> gives them one screen, one button. They approve it, you see it instantly. No more digging through emails wondering which file is the final one.</p>\n<p>Happy to show you how it works if it\'s ever on your radar.</p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    5: {
        'label': 'Breakup (Signs)',
        'A': {'subject': 'last one from me', 'template_name': '{prefix}_signs_seq5_a'},
        'B': {'subject': 'last one from me', 'template_name': '{prefix}_signs_seq5_b'},
        'body': '<p>Hi there,</p>\n<p>I\'ve reached out a few times about streamlining job approvals for sign shops, so I\'ll keep this short.</p>\n<p>If it\'s ever something you\'d like to explore, the door is always open. You can check out <a href="https://taggiq.com">TaggIQ</a> or book a quick chat:</p>\n<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>\n<p>Wishing you continued success with the business.</p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
}

APPAREL_TEMPLATES = {
    1: {
        'label': 'Cold Open (Apparel)',
        'A': {'subject': 'quick question about {{COMPANY}}', 'template_name': '{prefix}_apparel_seq1_a'},
        'B': {'subject': 'a question for the team at {{COMPANY}}', 'template_name': '{prefix}_apparel_seq1_b'},
        'body': '<p>Hi there,</p>\n<p>I spent 20 years in software before moving into embroidery and decorated apparel, and one thing that surprised me was how far behind the tools were.</p>\n<p>Quick question: how does your team collect sizes when a customer orders uniforms for a group? Most shops I\'ve spoken with across Ireland are still chasing sizes over email and spreadsheets.</p>\n<p>Curious how you manage it.</p>\n<p>If this isn\'t something you handle, feel free to pass it along to whoever manages production workflow.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com">TaggIQ</a><br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    2: {
        'label': 'Pain Point (Apparel)',
        'A': {'subject': 'the size collection problem', 'template_name': '{prefix}_apparel_seq2_a'},
        'B': {'subject': '{{FNAME}}, thought this might be relevant', 'template_name': '{prefix}_apparel_seq2_b'},
        'body': '<p>Hi there,</p>\n<p>I\'ve been talking with embroidery and apparel shop owners across Ireland about how they handle size collection and artwork approvals. Almost everyone describes some version of chasing clients for days before a job can move forward.</p>\n<p>I built a tool to fix this. It\'s called <a href="https://taggiq.com">TaggIQ</a> and it handles quotes, size collection, artwork approvals, orders and invoicing in one place.</p>\n<p>Happy to share more if you\'re dealing with the same thing.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com">TaggIQ</a><br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    3: {
        'label': 'Why TaggIQ (Apparel)',
        'A': {'subject': 'why I built TaggIQ', 'template_name': '{prefix}_apparel_seq3_a'},
        'B': {'subject': 'a different approach to running an apparel shop', 'template_name': '{prefix}_apparel_seq3_b'},
        'body': '<p>Hi there,</p>\n<p>I spent 20 years in software before getting into embroidery and apparel, and honestly the tools available didn\'t match how shops actually work.</p>\n<p>So I built TaggIQ. You send a quote, your customer picks their sizes through a simple link, approves the artwork in one click, and the job flows straight through to invoicing and payment. No spreadsheets, no chasing, no re-keying the same details three times.</p>\n<p>If you\'re curious, I\'d love to offer you a free trial. No commitment, no card required.</p>\n<p>You can sign up at <a href="https://taggiq.com/signup">taggiq.com</a> or book a quick 15-minute walkthrough:</p>\n<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    4: {
        'label': 'Size Collection Pain (Apparel)',
        'A': {'subject': 'chasing 40 people for sizes over email', 'template_name': '{prefix}_apparel_seq4_a'},
        'B': {'subject': 'one thing most apparel shops get wrong', 'template_name': '{prefix}_apparel_seq4_b'},
        'body': '<p>Hi there,</p>\n<p>Chasing 40 people for their uniform sizes over email, then manually entering it all into a spreadsheet. That\'s a full day gone on one order.</p>\n<p><a href="https://taggiq.com">TaggIQ</a> gives your customer a link. They pick their size, done. You see every response in one place, and the order is ready to go to production.</p>\n<p>Happy to show you how it works if it\'s ever on your radar.</p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    5: {
        'label': 'Breakup (Apparel)',
        'A': {'subject': 'last one from me', 'template_name': '{prefix}_apparel_seq5_a'},
        'B': {'subject': 'last one from me', 'template_name': '{prefix}_apparel_seq5_b'},
        'body': '<p>Hi there,</p>\n<p>I\'ve reached out a few times about streamlining size collection and artwork approvals for apparel shops, so I\'ll keep this short.</p>\n<p>If it\'s ever something you\'d like to explore, the door is always open. You can check out <a href="https://taggiq.com">TaggIQ</a> or book a quick chat:</p>\n<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>\n<p>Wishing you continued success with the business.</p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
}

PRINT_TEMPLATES = {
    1: {
        'label': 'Cold Open (Print)',
        'A': {'subject': 'quick question about {{COMPANY}}', 'template_name': '{prefix}_print_seq1_a'},
        'B': {'subject': 'a question for the team at {{COMPANY}}', 'template_name': '{prefix}_print_seq1_b'},
        'body': '<p>Hi there,</p>\n<p>I spent 20 years in software before moving into the print and promo industry, and one thing that surprised me was how far behind the tools were compared to every other sector.</p>\n<p>Quick question: how does your team handle artwork approvals? Most shops I\'ve spoken with across Ireland are still doing it over email and WhatsApp, which works until things start slipping through the cracks.</p>\n<p>Curious how you manage it.</p>\n<p>If this isn\'t something you handle, feel free to pass it along to whoever manages artwork and orders.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com">TaggIQ</a><br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    2: {
        'label': 'Pain Point (Print)',
        'A': {'subject': 'the artwork approval problem', 'template_name': '{prefix}_print_seq2_a'},
        'B': {'subject': '{{FNAME}}, thought this might be relevant', 'template_name': '{prefix}_print_seq2_b'},
        'body': '<p>Hi there,</p>\n<p>I\'ve been talking with print and promo shop owners across Ireland about how they handle artwork approvals and order tracking. Almost everyone describes some version of email back and forth until someone finally says yes.</p>\n<p>I built a tool to fix this. It\'s called <a href="https://taggiq.com">TaggIQ</a> and it keeps quotes, artwork approvals, orders and invoicing in one place.</p>\n<p>Happy to share more if you\'re dealing with the same thing.</p>\n<p>Prakash<br>Founder, <a href="https://taggiq.com">TaggIQ</a><br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    3: {
        'label': 'Why TaggIQ (Print)',
        'A': {'subject': 'why I built TaggIQ', 'template_name': '{prefix}_print_seq3_a'},
        'B': {'subject': 'a different approach to running a promo shop', 'template_name': '{prefix}_print_seq3_b'},
        'body': '<p>Hi there,</p>\n<p>I spent 20 years in software before getting into promo, and honestly the tools available didn\'t match how shops actually work.</p>\n<p>So I built TaggIQ. A customer finds you online, picks a product, uploads their logo. You send the quote, they approve the artwork in one click, and the job flows straight through to invoicing and payment. No re-keying, no chasing approvals over email, no separate systems.</p>\n<p>If you\'re curious, I\'d love to offer you a free trial. No commitment, no card required.</p>\n<p>You can sign up at <a href="https://taggiq.com/signup">taggiq.com</a> or book a quick 15-minute walkthrough:</p>\n<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    4: {
        'label': 'Quoting Pain (Print)',
        'A': {'subject': 'the hidden cost of quoting in promo', 'template_name': '{prefix}_print_seq4_a'},
        'B': {'subject': 'one thing most promo shops get wrong', 'template_name': '{prefix}_print_seq4_b'},
        'body': '<p>Hi there,</p>\n<p>Most shops I talk to spend 30 minutes building a quote, then re-type the same details into a purchase order, then again into an invoice. That\'s three times for the same job.</p>\n<p><a href="https://taggiq.com">TaggIQ</a> does it once. Quote becomes order becomes invoice, automatically. One flow, nothing re-keyed.</p>\n<p>Happy to show you how it works if it\'s ever on your radar.</p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
    5: {
        'label': 'Breakup (Print)',
        'A': {'subject': 'last one from me', 'template_name': '{prefix}_print_seq5_a'},
        'B': {'subject': 'last one from me', 'template_name': '{prefix}_print_seq5_b'},
        'body': '<p>Hi there,</p>\n<p>I\'ve reached out a few times about streamlining artwork approvals and order management for promo shops, so I\'ll keep this short.</p>\n<p>If it\'s ever something you\'d like to explore, the door is always open. You can check out <a href="https://taggiq.com">TaggIQ</a> or book a quick chat:</p>\n<p><a href="https://calendar.app.google/fzQ5iQLGHakimfjv7">Schedule a Demo with Prakash</a></p>\n<p>Wishing you continued success with the business.</p>\n<p>Prakash<br>Founder, TaggIQ<br><a href="https://taggiq.com">taggiq.com</a></p>',
    },
}

# ── FP FRANCHISE RECRUITMENT ─────────────────────────────────────────────

FP_RECRUITMENT = {
    1: {
        'label': 'Re-Engagement',
        'A': {'subject': 'Fully Promoted Ireland - quick update, {{FNAME}}', 'template_name': 'fp_reengagement_a'},
        'B': {'subject': '{{FNAME}}, remember your franchise enquiry?', 'template_name': 'fp_reengagement_b'},
        'body': '<p>Hi {{FNAME}},</p>\n\n<p>You enquired about the Fully Promoted franchise in Ireland back in {{YEAR}}. At the time, we weren\'t quite ready to launch here.</p>\n\n<p>Now we are.</p>\n\n<p>Fully Promoted is the world\'s largest promotional products franchise - #1 in our category for 25 years running, with over 300 locations worldwide. And we\'re now looking for franchise partners across Ireland.</p>\n\n<p>I\'m Prakash, the Master Franchisee for Ireland. Would love to have a quick chat and fill you in, or send over the franchise brochure if you\'d prefer a read first.</p>\n\n<p>Just hit reply either way. Would be great to hear from you.</p>\n\n<p>Cheers,<br>\nPrakash Inani<br>\nMaster Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>\nUnit A20, Kingswood Business Park, Dublin<br>\n<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>',
    },
    2: {
        'label': 'Business Case',
        'A': {'subject': 'Quick thought on the Irish market, {{FNAME}}', 'template_name': 'fp_business_case_a'},
        'B': {'subject': 'Why I picked Fully Promoted for Ireland', 'template_name': 'fp_business_case_b'},
        'body': '<p>Hi {{FNAME}},</p>\n\n<p>Prakash here from Fully Promoted Ireland. You enquired about a franchise with us a while back, so I wanted to reach out.</p>\n\n<p>I\'m the Master Franchisee for Ireland and we\'re now actively looking for franchise partners. The thing I love about this model is that every business needs branded products, uniforms, and marketing materials, and they come back for more every quarter. It\'s a proper recurring revenue business.</p>\n\n<p>Would be great to have a quick chat if you\'re open to it. Here\'s a link to grab a time that suits you: <a href="https://calendar.app.google/yFLeFoyP3XscHsBs8">https://calendar.app.google/yFLeFoyP3XscHsBs8</a></p>\n\n<p>Cheers,<br>\nPrakash Inani<br>\nMaster Franchisee, <a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>\nUnit A20, Kingswood Business Park, Dublin<br>\n<a href="https://fullypromoted.ie">fullypromoted.ie</a></p>',
    },
    3: {
        'label': 'Social Proof',
        'A': {'subject': 'How a first-timer built a million-dollar franchise', 'template_name': 'fp_social_proof_a'},
        'B': {'subject': 'Something I thought you\'d find interesting, {{FNAME}}', 'template_name': 'fp_social_proof_b'},
        'body': '<p>Hi {{FNAME}},</p>\n\n<p>Thought you might find this relevant.</p>\n\n<p>Michelle Bottino left her corporate career in 2018 to open a Fully Promoted store in Illinois. No industry experience. Within a few years, she\'d built it into a million-dollar operation. Another franchisee in Ohio grew 72% in a single year.</p>\n\n<p>Most of our successful owners came from completely different backgrounds. The system handles the heavy lifting - your job is building relationships with local businesses.</p>\n\n<p>I\'m putting together the first group of franchise partners for Ireland. Would love to include you in that conversation if the timing works.</p>\n\n<p>Worth a quick chat?</p>\n\n<p>Cheers,<br>\nPrakash<br>\n<a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>\nUnit A20, Kingswood Business Park, Dublin</p>',
    },
    4: {
        'label': 'Personal Story',
        'A': {'subject': 'Quick question, {{FNAME}}', 'template_name': 'fp_personal_story_a'},
        'B': {'subject': '{{FNAME}}, one last thought', 'template_name': 'fp_personal_story_b'},
        'body': '<p>Hi {{FNAME}},</p>\n\n<p>I know I\'ve been in your inbox a few times, so I\'ll keep this short.</p>\n\n<p>Before I got into this industry, I spent 20 years in software. I had no background in print or promotional products. But I saw how every business in Ireland needs branded gear, uniforms, marketing materials, and they keep coming back for more. That\'s what convinced me.</p>\n\n<p>If you\'ve ever thought about running your own business but weren\'t sure where to start, this is worth a conversation. No experience needed, and there\'s a full training and support system behind you from day one.</p>\n\n<p>Happy to have a quick chat if you\'re curious. Here\'s a link to grab a time: <a href="https://calendar.app.google/yFLeFoyP3XscHsBs8">Book a call with Prakash</a></p>\n\n<p>Cheers,<br>\nPrakash<br>\n<a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>\nUnit A20, Kingswood Business Park, Dublin</p>',
    },
    5: {
        'label': 'Breakup',
        'A': {'subject': 'Closing your file, {{FNAME}}', 'template_name': 'fp_breakup_a'},
        'B': {'subject': 'Closing your file, {{FNAME}}', 'template_name': 'fp_breakup_b'},
        'body': '<p>Hi {{FNAME}},</p>\n\n<p>I\'ve reached out a few times about Fully Promoted Ireland and haven\'t heard back, so I\'ll assume the timing isn\'t right.</p>\n\n<p>Completely understand. If things change down the road, my door is always open. Just reply to this email anytime.</p>\n\n<p>Wishing you all the best, {{FNAME}}.</p>\n\n<p>Cheers,<br>\nPrakash<br>\n<a href="https://fullypromoted.ie">Fully Promoted Ireland</a><br>\nUnit A20, Kingswood Business Park, Dublin</p>',
    },
}


# ── CAMPAIGN -> TEMPLATE MAPPING ─────────────────────────────────────────

def _resolve_templates(templates, prefix=''):
    """Resolve {prefix} in template_name fields."""
    resolved = {}
    for seq, data in templates.items():
        resolved[seq] = {
            'label': data['label'],
            'body': data['body'],
            'A': {
                'subject': data['A']['subject'],
                'template_name': data['A']['template_name'].format(prefix=prefix),
            },
            'B': {
                'subject': data['B']['subject'],
                'template_name': data['B']['template_name'].format(prefix=prefix),
            },
        }
    return resolved


CAMPAIGN_TEMPLATES = {
    # BNI campaigns
    'TaggIQ BNI': BNI_BASE,
    'TaggIQ BNI Promo Global': BNI_BASE,
    'TaggIQ BNI Embroidery Global': BNI_EMBROIDERY,
    # Ireland cold campaigns
    'Signs & Signage': lambda: _resolve_templates(SIGNS_TEMPLATES, 'ireland'),
    'Ireland — Apparel': lambda: _resolve_templates(APPAREL_TEMPLATES, 'ireland'),
    'Ireland — Print': lambda: _resolve_templates(PRINT_TEMPLATES, 'ireland'),
    # London cold campaigns
    'London — Signs': lambda: _resolve_templates(SIGNS_TEMPLATES, 'london'),
    'London — Apparel': lambda: _resolve_templates(APPAREL_TEMPLATES, 'london'),
    'London — Print': lambda: _resolve_templates(PRINT_TEMPLATES, 'london'),
    # FP campaigns
    'FP Ireland Franchise': FP_RECRUITMENT,
}


class Command(BaseCommand):
    help = 'Seed EmailTemplate records from hardcoded sender script templates'

    def add_arguments(self, parser):
        parser.add_argument('--campaign', help='Only seed for this campaign (name substring)')
        parser.add_argument('--dry-run', action='store_true', help='Preview without creating')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        campaign_filter = options.get('campaign')

        created = 0
        skipped = 0

        for name_match, templates_source in CAMPAIGN_TEMPLATES.items():
            # Find campaign by name substring
            campaign = Campaign.objects.filter(name__icontains=name_match).first()
            if not campaign:
                self.stderr.write(self.style.WARNING(f'Campaign not found: {name_match}'))
                continue

            if campaign_filter and campaign_filter.lower() not in campaign.name.lower():
                continue

            # Resolve callable templates (for prefix substitution)
            templates = templates_source() if callable(templates_source) else templates_source

            self.stdout.write(f'\n{campaign.name}:')

            for seq_num, data in templates.items():
                for variant in ['A', 'B']:
                    variant_data = data[variant]
                    exists = EmailTemplate.objects.filter(
                        campaign=campaign,
                        sequence_number=seq_num,
                        ab_variant=variant,
                    ).exists()

                    if exists:
                        skipped += 1
                        continue

                    if dry_run:
                        self.stdout.write(f'  [DRY] Seq {seq_num}{variant}: {variant_data["subject"][:60]}')
                        created += 1
                        continue

                    EmailTemplate.objects.create(
                        campaign=campaign,
                        sequence_number=seq_num,
                        ab_variant=variant,
                        subject_template=variant_data['subject'],
                        body_html_template=data['body'],
                        template_name=variant_data['template_name'],
                        sequence_label=data['label'],
                        is_active=True,
                    )
                    created += 1
                    self.stdout.write(f'  Seq {seq_num}{variant}: {variant_data["subject"][:60]}')

        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{prefix}Created: {created}, Skipped (existing): {skipped}'
        ))
