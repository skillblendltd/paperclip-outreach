"""
Batch-author bespoke HTML for a range of SocialPosts using three proven
template patterns (hero dark, native warm, gradient-header card).

Usage:
    python manage.py batch_design --from 5 --to 30
    python manage.py batch_design --from 5 --to 30 --render
    python manage.py batch_design --from 5 --to 30 --render --dry-run

Each post is assigned a tier from TIER_MAP. The matching template string
is rendered with per-post slots (headline, kicker, body items, etc.) from
POST_SLOTS. Output written to social_studio/rendered_html/post_NN.html.
If --render is passed, immediately invokes the renderer to produce PNGs.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from social_studio.models import SocialPost


BASE_DIR = Path(settings.BASE_DIR) / 'social_studio'
OUT_DIR = BASE_DIR / 'rendered_html'


# --------------------------------------------------------------------------- #
# TIER MAP - which template each post uses
# --------------------------------------------------------------------------- #

TIER_HERO = 'hero_dark'            # Post 2 style - dark charcoal, gradients, step cards
TIER_NATIVE = 'native_warm'        # Post 3 style - warm cream, quote mark, headshot
TIER_CARD = 'card_gradient'        # Post 4 style - gradient header band, color-coded list

TIER_MAP: dict[int, str] = {
    5: TIER_CARD,      # Social proof - customer win (reconciliation)
    6: TIER_CARD,      # Industry - quoting time poll
    7: TIER_HERO,      # Product - artwork approval flow
    8: TIER_NATIVE,    # Behind scenes - size collections
    9: TIER_CARD,      # Industry - hidden cost of free tools
    10: TIER_HERO,     # Product - pipeline board
    11: TIER_CARD,     # Social proof - how many tools poll
    12: TIER_HERO,     # Product - SourceIQ search
    13: TIER_NATIVE,   # Behind scenes - almost built wrong product
    14: TIER_CARD,     # Industry - decoration methods comparison
    15: TIER_CARD,     # Social proof - 2000 quotes milestone
    16: TIER_CARD,     # Industry - cost per impression
    17: TIER_HERO,     # Product - order tracking moment
    18: TIER_NATIVE,   # Behind scenes - first 10 customers
    19: TIER_CARD,     # Industry - supplier data problem
    20: TIER_HERO,     # Product - before/after workflow
    21: TIER_CARD,     # Social proof - conversation we have
    22: TIER_HERO,     # Product - 200 polo quote walkthrough
    23: TIER_NATIVE,   # Behind scenes - Dublin not SV
    24: TIER_CARD,     # Industry - 3 weekly reports
    25: TIER_CARD,     # Product - EOD quote
    26: TIER_CARD,     # Social proof - switching to TaggIQ
    27: TIER_CARD,     # Product - wrong invoice story
    28: TIER_NATIVE,   # Behind scenes - feature request process
    29: TIER_CARD,     # Industry - quote by program
    30: TIER_CARD,     # Social proof - call to action
}


# --------------------------------------------------------------------------- #
# PER-POST SLOTS - short custom content per post
# --------------------------------------------------------------------------- #

POST_SLOTS: dict[int, dict] = {
    5: {
        'tag': 'Customer win',
        'kicker': 'Monday Mornings',
        'headline_a': 'From reconciliation headaches',
        'headline_b': 'to actually selling.',
        'items': [
            ('1', 'No more month-end marathons', 'Invoices reconcile automatically against payments.'),
            ('2', 'Sunday nights belong to you again', 'Not spreadsheet detective work on Q4 numbers.'),
            ('3', 'Team knows the true cash position', 'In real time, not when the bookkeeper catches up.'),
            ('4', 'Focus shifts back to revenue', 'The work only you can do.'),
        ],
        'hashtags': '#TaggIQ  ·  #PromoProducts  ·  #TimeBack',
    },
    6: {
        'tag': 'Poll',
        'kicker': 'How long does a quote take?',
        'headline_a': 'Quoting time,',
        'headline_b': 'honestly.',
        'items': [
            ('A', 'Under 10 minutes', 'You run a tight ship. What is your secret?'),
            ('B', '10 to 30 minutes', 'Reasonable for most orders.'),
            ('C', '30 to 60 minutes', 'Something to fix. Supplier catalog browsing?'),
            ('D', 'Over an hour', 'No judgement. Complex multi-decoration orders.'),
        ],
        'hashtags': '#PromoProducts  ·  #Quoting  ·  #TaggIQ',
    },
    7: {
        'tag': 'Product in action',
        'big_a': '10',
        'big_a_unit': 'Email ping-pong steps',
        'big_b': '1',
        'big_b_unit': 'Approval link',
        'title_a': 'Artwork approval, simplified.',
        'title_b': 'Upload once. Approve once. Ship confidently.',
        'steps': [
            ('Upload proof to TaggIQ', 'One file, one source of truth'),
            ('Customer gets a single link', 'No email thread, no "reply all"'),
            ('Customer approves or requests edit', 'Changes logged, versioned'),
            ('You see it instantly', 'Notification, not email archaeology'),
            ('Production is 100% confident', 'Only approved version is live'),
        ],
        'hashtags': '#TaggIQ  ·  #ArtworkApproval  ·  #PromoProducts',
    },
    8: {
        'tag': 'Behind the scenes',
        'quote_a': 'We shipped a feature nobody asked for.',
        'quote_b': 'Everyone needed it.',
        'attribution_role': 'Founder, TaggIQ  ·  Shipping what shops need',
        'closer_strong': 'Size collections',
        'closer_body': 'Custom apparel orders need size breakdowns that flow from quote to order to PO to invoice with zero manual re-entry. Spreadsheets cannot do this. We built it because our users bled from it daily.',
        'hashtags': '#FounderStory  ·  #TaggIQ  ·  #BuildInPublic',
    },
    9: {
        'tag': 'Margin check',
        'kicker': 'Hidden cost',
        'headline_a': 'The real price of',
        'headline_b': 'free tools.',
        'items': [
            ('1', '10+ hours weekly on manual entry', 'Quoting, invoicing, tracking. All by hand.'),
            ('2', 'Lost deals from slow quotes', 'Every hour is a sale you did not close.'),
            ('3', 'Billing errors from manual math', 'Over or undercharge. Both cost you.'),
            ('4', 'Month-end reconciliation marathons', 'Your Sunday afternoon is not actually free.'),
            ('5', 'Zero visibility into pipeline', 'Where is your cash today? Really?'),
        ],
        'hashtags': '#PromoProducts  ·  #TrueCost  ·  #TaggIQ',
    },
    10: {
        'tag': 'Product in action',
        'big_a': '4',
        'big_a_unit': 'Apps before',
        'big_b': '1',
        'big_b_unit': 'Screen with TaggIQ',
        'title_a': 'Your entire pipeline.',
        'title_b': 'One screen.',
        'steps': [
            ('Quotes waiting for approval', 'Who is sitting on what, for how long'),
            ('Orders in production', 'Supplier, decoration stage, ship date'),
            ('Invoices pending payment', 'Age buckets, overdue flags'),
            ('Cash flow at a glance', 'Real time, not month-end guesswork'),
            ('Every team member, same view', 'No more "what did you say?" standups'),
        ],
        'hashtags': '#TaggIQ  ·  #Pipeline  ·  #PromoProducts',
    },
    11: {
        'tag': 'Poll',
        'kicker': 'Tool sprawl',
        'headline_a': 'How many tools',
        'headline_b': 'does your shop run?',
        'items': [
            ('A', '1 to 3 tools', 'Lean and integrated. Rare.'),
            ('B', '4 to 6 tools', 'Normal. Manageable with discipline.'),
            ('C', '7 to 10 tools', 'Tool fatigue and copy-paste errors start here.'),
            ('D', '10+ tools', 'Nobody knows where the source of truth lives.'),
        ],
        'hashtags': '#PromoProducts  ·  #ToolFatigue  ·  #TaggIQ',
    },
    12: {
        'tag': 'SourceIQ',
        'big_a': '500k',
        'big_a_unit': 'Products searchable',
        'big_b': '50+',
        'big_b_unit': 'Suppliers connected',
        'title_a': 'Stop tab-hopping between',
        'title_b': 'supplier websites.',
        'steps': [
            ('Search by product, color, size, or SKU', 'Across every connected supplier at once'),
            ('Live pricing and stock', 'Yesterday spreadsheets will not help you'),
            ('Filter by decoration method', 'Only see products that fit the job'),
            ('Add to quote with one click', 'Line items and cost auto-populate'),
            ('Compare alternatives side by side', 'Before the customer asks'),
        ],
        'hashtags': '#SourceIQ  ·  #TaggIQ  ·  #PromoProducts',
    },
    13: {
        'tag': 'Lessons learned',
        'quote_a': 'We almost built',
        'quote_b': 'the wrong product.',
        'attribution_role': 'Founder, TaggIQ  ·  Listening to real shops',
        'closer_strong': 'First instinct: generic promo CRM',
        'closer_body': 'Then we talked to 30 real shops and realised CRM was already solved. The bleeding was in quote-to-invoice, not lead capture. We pivoted hard. That conversation saved us 12 months.',
        'hashtags': '#FounderStory  ·  #BuildInPublic  ·  #TaggIQ',
    },
    14: {
        'tag': 'Decoration 101',
        'kicker': 'Method guide',
        'headline_a': 'Screen print · Embroidery',
        'headline_b': 'DTG · Heat transfer.',
        'items': [
            ('1', 'Screen printing', 'Cheapest at volume. Setup cost per color. 100+ units.'),
            ('2', 'Embroidery', 'Premium feel. Stitch-count pricing. Durable on polos, caps.'),
            ('3', 'Direct-to-garment (DTG)', 'Full-color, no setup. Best under 50 units or detailed art.'),
            ('4', 'Heat transfer / DTF', 'Fast turnaround, small runs, names and numbers.'),
        ],
        'hashtags': '#PromoProducts  ·  #Decoration  ·  #TaggIQ',
    },
    15: {
        'tag': 'Milestone',
        'kicker': 'Milestone unlocked',
        'headline_a': '2,000 quotes',
        'headline_b': 'processed. And counting.',
        'items': [
            ('1', 'Real volume, real shops', 'Not vanity metrics. Real working distributors.'),
            ('2', 'Average quote under 4 minutes', 'From search to send, including artwork'),
            ('3', 'Thousands of supplier lookups', 'SourceIQ is earning its keep'),
            ('4', 'Thank you to the first believers', 'You know who you are. This is for you.'),
        ],
        'hashtags': '#TaggIQ  ·  #Milestone  ·  #Thankyou',
    },
    16: {
        'tag': 'Margin math',
        'kicker': 'Unit economics',
        'headline_a': 'True cost per impression,',
        'headline_b': 'done right.',
        'items': [
            ('1', 'Total order cost, all-in', 'Product + decoration + setup + freight + labor.'),
            ('2', 'Divide by estimated impressions', 'Lifetime exposure, not just recipient count.'),
            ('3', 'Benchmark against other media', 'Print, radio, social. Promo usually wins.'),
            ('4', 'Show the customer the math', 'They remember. They come back.'),
        ],
        'hashtags': '#PromoProducts  ·  #MarginMath  ·  #TaggIQ',
    },
    17: {
        'tag': 'Product in action',
        'big_a': '20',
        'big_a_unit': 'Minutes on hold (old way)',
        'big_b': '3',
        'big_b_unit': 'Seconds in TaggIQ',
        'title_a': '"Where is my order?"',
        'title_b': 'Answer instantly.',
        'steps': [
            ('Customer asks for status', 'Phone, email, or chat'),
            ('You open the order in TaggIQ', 'One click from the pipeline board'),
            ('Live stage shown', 'Supplier received, decoration started, shipped'),
            ('Share a customer-facing link', 'They can check it themselves next time'),
            ('Close the loop with confidence', 'No more "I will call the supplier"'),
        ],
        'hashtags': '#TaggIQ  ·  #OrderTracking  ·  #PromoProducts',
    },
    18: {
        'tag': 'Lessons learned',
        'quote_a': 'Your first 10 customers',
        'quote_b': 'teach you everything.',
        'attribution_role': 'Founder, TaggIQ  ·  Listening, not launching',
        'closer_strong': 'The playbook nobody tells you',
        'closer_body': 'Our first 10 customers reshaped the roadmap three times. We shipped features we never would have imagined. We killed features we thought were essential. If you are building anything, talk to your first 10 like your life depends on it.',
        'hashtags': '#FounderStory  ·  #BuildInPublic  ·  #TaggIQ',
    },
    19: {
        'tag': 'Industry data',
        'kicker': 'The hidden problem',
        'headline_a': 'The promo industry',
        'headline_b': 'has a data problem.',
        'items': [
            ('1', 'Every supplier has a different format', 'CSV, XML, PDF, email attachment, or nothing.'),
            ('2', 'Catalog updates are manual', 'Your spreadsheet is always out of date.'),
            ('3', 'Stock and pricing drift daily', 'Quoting from last week means losing money.'),
            ('4', 'Nobody normalises across brands', 'Until now. SourceIQ does this automatically.'),
        ],
        'hashtags': '#PromoProducts  ·  #SupplierData  ·  #TaggIQ',
    },
    20: {
        'tag': 'Before vs after',
        'big_a': '7',
        'big_a_unit': 'Steps the old way',
        'big_b': '2',
        'big_b_unit': 'Clicks with TaggIQ',
        'title_a': 'Quote, approve, deliver.',
        'title_b': 'Without the swivel-chair.',
        'steps': [
            ('Quote built natively in TaggIQ', 'No Excel, no copy-paste'),
            ('Customer opens a live presentation', 'Not a PDF attachment they cannot find'),
            ('Approval click stays in the app', 'No email thread to archive'),
            ('Order drops into production', 'With artwork, sizes, supplier auto-routed'),
            ('Invoice fires on delivery', 'Connected to your accounting'),
        ],
        'hashtags': '#TaggIQ  ·  #Workflow  ·  #PromoProducts',
    },
    21: {
        'tag': 'Conversation',
        'kicker': 'The question we hear',
        'headline_a': '"We tried X.',
        'headline_b': 'What makes TaggIQ different?"',
        'items': [
            ('1', 'Built by someone who ran a promo shop', 'Not a generic CRM bolted onto print.'),
            ('2', 'Every screen is promo-specific', 'Decoration pricing. Artwork. Size runs. Suppliers.'),
            ('3', 'SourceIQ ships with 500k products', 'No spreadsheet imports, no stale data.'),
            ('4', 'We ship weekly, we listen daily', 'Your feature request has a real chance.'),
        ],
        'hashtags': '#TaggIQ  ·  #PromoProducts  ·  #Comparison',
    },
    22: {
        'tag': 'Walkthrough',
        'big_a': '200',
        'big_a_unit': 'Branded polos requested',
        'big_b': '3',
        'big_b_unit': 'Minutes to quoted',
        'title_a': '"I need 200 polos',
        'title_b': 'for our company retreat."',
        'steps': [
            ('Search polo styles in SourceIQ', 'Filter by price, brand, size availability'),
            ('Pick the polo, add to quote', 'Line item and base cost auto-fill'),
            ('Add embroidery with stitch count', 'Decoration math calculates itself'),
            ('Enter size breakdown', '30 S, 50 M, 80 L, 40 XL. Done.'),
            ('Send live presentation link', 'Customer clicks approve from their phone'),
        ],
        'hashtags': '#TaggIQ  ·  #Quoting  ·  #PromoProducts',
    },
    23: {
        'tag': 'Founder note',
        'quote_a': 'Dublin is not',
        'quote_b': 'Silicon Valley.',
        'attribution_role': 'Founder, TaggIQ  ·  Building from Dublin, Ireland',
        'closer_strong': 'No promo tech hub. No meetup. No handbook.',
        'closer_body': 'Which means every decision comes from first principles and real customer conversations, not pattern-matching on the last hot SaaS. We might move slower. We also build exactly what shops need, not what investors want to hear.',
        'hashtags': '#FounderStory  ·  #Dublin  ·  #TaggIQ',
    },
    24: {
        'tag': 'Ops playbook',
        'kicker': 'Weekly rituals',
        'headline_a': '3 reports every',
        'headline_b': 'distributor should run.',
        'items': [
            ('1', 'Pipeline value by stage', 'How much cash is parked where?'),
            ('2', 'Overdue invoices', 'Chase before month-end, not after.'),
            ('3', 'Quote-to-close conversion', 'Which reps, which products, which decorators?'),
            ('4', 'Bonus: supplier lead-time drift', 'Catch delays before the customer does.'),
        ],
        'hashtags': '#PromoProducts  ·  #Ops  ·  #TaggIQ',
    },
    25: {
        'tag': 'Product in action',
        'kicker': 'EOD quote',
        'headline_a': '"Can you send me a',
        'headline_b': 'quote by end of day?"',
        'items': [
            ('1', 'Used to stress us out', 'Usually meant dropping everything else.'),
            ('2', 'Now: 3 minutes total', 'Search, add, decorate, send. Done.'),
            ('3', 'Live presentation link', 'Customer can show their team instantly.'),
            ('4', 'Approval returns directly to the order', 'No manual copy-paste into the production queue.'),
        ],
        'hashtags': '#TaggIQ  ·  #Quoting  ·  #PromoProducts',
    },
    26: {
        'tag': 'Migration',
        'kicker': 'Switching to TaggIQ',
        'headline_a': 'What onboarding',
        'headline_b': 'actually looks like.',
        'items': [
            ('1', 'Day 1: Connect your suppliers', 'SourceIQ pulls in catalogs automatically.'),
            ('2', 'Day 2: Import your customers', 'CSV or direct sync from your current tool.'),
            ('3', 'Day 3: Build your first quote', 'Prakash is on the other end of the chat.'),
            ('4', 'Week 1: Full pipeline running', 'No big bang cutover. Old tool stays up until you trust us.'),
        ],
        'hashtags': '#TaggIQ  ·  #Migration  ·  #PromoProducts',
    },
    27: {
        'tag': 'True story',
        'kicker': 'Invoice horror',
        'headline_a': 'Every distributor',
        'headline_b': 'has a wrong-invoice story.',
        'items': [
            ('1', 'Wrong quantity', 'Quote had 500, invoice had 250. Customer noticed.'),
            ('2', 'Wrong decoration method', 'Billed screen print, delivered DTG, lost margin.'),
            ('3', 'Missing setup fees', 'Forgot to pass them through. Ate the cost.'),
            ('4', 'Wrong customer entirely', 'Awkward phone call at month end.'),
        ],
        'hashtags': '#PromoProducts  ·  #Invoicing  ·  #TaggIQ',
    },
    28: {
        'tag': 'Product process',
        'quote_a': 'How we decide',
        'quote_b': 'what to build next.',
        'attribution_role': 'Founder, TaggIQ  ·  Listening weekly',
        'closer_strong': 'Every Friday, we read every request.',
        'closer_body': 'We rank by how often we hear it, how much pain it causes, and whether it compounds across customers. No voting widget, no elaborate roadmap tool. Just a conversation and a list. That is how size collections shipped in three weeks.',
        'hashtags': '#FounderStory  ·  #BuildInPublic  ·  #TaggIQ',
    },
    29: {
        'tag': 'Margin thinking',
        'kicker': 'Pricing reframe',
        'headline_a': 'Stop quoting by the piece.',
        'headline_b': 'Start quoting by the program.',
        'items': [
            ('1', 'Programs include multiple touches', 'Reorders, new hires, seasonal refreshes.'),
            ('2', 'Lock in pricing for a year', 'Predictable margin, predictable supply.'),
            ('3', 'Bundle decoration setup', 'Amortised across the program, not per order.'),
            ('4', 'You become the brand partner', 'Not the vendor of the month.'),
        ],
        'hashtags': '#PromoProducts  ·  #Pricing  ·  #TaggIQ',
    },
    30: {
        'tag': 'A real ask',
        'kicker': '6 weeks of content',
        'headline_a': 'If you run a promo shop,',
        'headline_b': 'let us talk.',
        'items': [
            ('1', 'Free 20-minute demo', 'Tailored to your actual workflow, not a slide deck.'),
            ('2', '3 months free if you switch', 'No credit card, no pressure.'),
            ('3', 'Direct line to the founder', 'Prakash answers the chat personally.'),
            ('4', 'We listen more than we pitch', 'Honest conversation about fit.'),
        ],
        'hashtags': '#TaggIQ  ·  #Demo  ·  #PromoProducts',
    },
}


# --------------------------------------------------------------------------- #
# TEMPLATES - inline strings so the command is self-contained
# --------------------------------------------------------------------------- #

HERO_DARK_TEMPLATE = '''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@font-face {{ font-family: 'Poppins'; font-weight: 700; src: url('file:///app/social_studio/static/social/taggiq/Poppins-Bold.ttf') format('truetype'); font-display: block; }}
@font-face {{ font-family: 'Poppins'; font-weight: 600; src: url('file:///app/social_studio/static/social/taggiq/Poppins-SemiBold.ttf') format('truetype'); font-display: block; }}
@font-face {{ font-family: 'Inter'; font-weight: 400; src: url('file:///app/social_studio/static/social/taggiq/Inter-Regular.ttf') format('truetype'); font-display: block; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1200px; height: 1200px; overflow: hidden; font-family: 'Inter', sans-serif; color: #FFFFFF; background: #0F172A; -webkit-font-smoothing: antialiased; }}
.canvas {{ width: 1200px; height: 1200px; padding: 80px; display: flex; flex-direction: column; position: relative; background: radial-gradient(circle at 85% 15%, rgba(124, 58, 237, 0.35) 0%, rgba(124, 58, 237, 0) 45%), radial-gradient(circle at 10% 90%, rgba(18, 180, 136, 0.18) 0%, rgba(18, 180, 136, 0) 40%), linear-gradient(135deg, #1E2030 0%, #0F172A 100%); }}
.grid-pattern {{ position: absolute; inset: 0; background-image: radial-gradient(circle, rgba(255, 255, 255, 0.06) 1.5px, transparent 1.5px); background-size: 32px 32px; pointer-events: none; }}
.header {{ position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; margin-bottom: 40px; }}
.logo {{ height: 56px; }}
.tag {{ background: rgba(124, 58, 237, 0.22); color: #C4A5FF; border: 1px solid rgba(124, 58, 237, 0.45); padding: 10px 22px; border-radius: 999px; font-weight: 500; font-size: 14px; letter-spacing: 0.16em; text-transform: uppercase; }}
.contrast {{ position: relative; z-index: 2; display: flex; align-items: center; justify-content: center; gap: 64px; margin-bottom: 32px; }}
.contrast-num {{ font-family: 'Poppins', sans-serif; font-weight: 700; line-height: 0.92; letter-spacing: -0.035em; text-align: center; }}
.contrast-num .val {{ font-size: 200px; display: block; color: #475569; text-decoration: line-through; text-decoration-thickness: 10px; text-decoration-color: #F44336; }}
.contrast-num.good .val {{ color: transparent; background: linear-gradient(135deg, #34D399 0%, #12B488 100%); -webkit-background-clip: text; background-clip: text; text-decoration: none; }}
.contrast-num .unit {{ display: block; font-size: 18px; font-weight: 500; color: #94A3B8; text-decoration: none; letter-spacing: 0.14em; text-transform: uppercase; margin-top: 12px; }}
.contrast-num.good .unit {{ color: #6EE7B7; }}
.arrow {{ font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 72px; background: linear-gradient(135deg, #7C3AED 0%, #12B488 100%); -webkit-background-clip: text; background-clip: text; color: transparent; line-height: 0.9; }}
.title {{ position: relative; z-index: 2; font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 38px; line-height: 1.15; color: #F8FAFC; text-align: center; margin-bottom: 44px; letter-spacing: -0.01em; }}
.title .accent-text {{ background: linear-gradient(120deg, #A78BFA 0%, #6EE7B7 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.steps {{ position: relative; z-index: 2; display: grid; grid-template-columns: 1fr 1fr; gap: 16px 20px; flex: 1; }}
.step {{ display: flex; align-items: center; gap: 18px; padding: 22px 26px; background: rgba(255, 255, 255, 0.035); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; }}
.step:nth-child(1) {{ --c: #60A5FA; }}
.step:nth-child(2) {{ --c: #A78BFA; }}
.step:nth-child(3) {{ --c: #FBBF24; }}
.step:nth-child(4) {{ --c: #34D399; }}
.step:nth-child(5) {{ --c: #F472B6; grid-column: 1 / -1; }}
.step-num {{ flex-shrink: 0; width: 40px; height: 40px; border-radius: 10px; background: color-mix(in srgb, var(--c) 18%, transparent); color: var(--c); display: flex; align-items: center; justify-content: center; font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 18px; }}
.step-text {{ font-family: 'Inter', sans-serif; font-weight: 400; font-size: 16px; color: #CBD5E1; line-height: 1.3; }}
.step-text strong {{ font-family: 'Poppins', sans-serif; font-weight: 600; color: #F8FAFC; display: block; font-size: 18px; margin-bottom: 2px; }}
.footer {{ position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; padding-top: 20px; margin-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); }}
.footer .hashtags {{ font-weight: 500; font-size: 14px; color: #94A3B8; }}
.footer .url {{ font-weight: 600; font-size: 14px; color: #C4A5FF; }}
</style>
</head>
<body>
<div class="canvas">
    <div class="grid-pattern"></div>
    <div class="header">
        <img class="logo" src="file:///app/social_studio/static/social/taggiq/logo.png" alt="TaggIQ">
        <div class="tag">{tag}</div>
    </div>
    <div class="contrast">
        <div class="contrast-num"><span class="val">{big_a}</span><span class="unit">{big_a_unit}</span></div>
        <div class="arrow">→</div>
        <div class="contrast-num good"><span class="val">{big_b}</span><span class="unit">{big_b_unit}</span></div>
    </div>
    <div class="title">{title_a}  <span class="accent-text">{title_b}</span></div>
    <div class="steps">
        {steps_html}
    </div>
    <div class="footer">
        <div class="hashtags">{hashtags}</div>
        <div class="url">taggiq.com</div>
    </div>
</div>
</body>
</html>
'''


NATIVE_WARM_TEMPLATE = '''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@font-face {{ font-family: 'Poppins'; font-weight: 700; src: url('file:///app/social_studio/static/social/taggiq/Poppins-Bold.ttf') format('truetype'); font-display: block; }}
@font-face {{ font-family: 'Poppins'; font-weight: 600; src: url('file:///app/social_studio/static/social/taggiq/Poppins-SemiBold.ttf') format('truetype'); font-display: block; }}
@font-face {{ font-family: 'Inter'; font-weight: 400; src: url('file:///app/social_studio/static/social/taggiq/Inter-Regular.ttf') format('truetype'); font-display: block; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1200px; height: 1200px; overflow: hidden; font-family: 'Inter', sans-serif; color: #1E2030; background: #FAF8F5; -webkit-font-smoothing: antialiased; }}
.canvas {{ width: 1200px; height: 1200px; padding: 80px; display: flex; flex-direction: column; position: relative; background: radial-gradient(circle at 90% 8%, rgba(244, 114, 182, 0.22) 0%, rgba(244, 114, 182, 0) 35%), radial-gradient(circle at 12% 75%, rgba(124, 58, 237, 0.18) 0%, rgba(124, 58, 237, 0) 40%), #FAF8F5; }}
.deco-dots {{ position: absolute; bottom: 80px; right: 80px; width: 200px; height: 200px; pointer-events: none; opacity: 0.4; }}
.header {{ position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; margin-bottom: 100px; }}
.logo {{ height: 56px; }}
.tag {{ background: linear-gradient(135deg, #F3F0FF 0%, #FCE7F3 100%); color: #7C3AED; padding: 10px 22px; border-radius: 999px; font-weight: 500; font-size: 14px; letter-spacing: 0.16em; text-transform: uppercase; border: 1px solid #DDCAFF; }}
.content {{ position: relative; z-index: 2; flex: 1; display: flex; flex-direction: column; justify-content: center; }}
.quote-mark {{ font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 220px; line-height: 0.5; background: linear-gradient(135deg, #7C3AED 0%, #F472B6 100%); -webkit-background-clip: text; background-clip: text; color: transparent; margin-bottom: 28px; }}
.quote {{ font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 60px; line-height: 1.12; color: #1E2030; letter-spacing: -0.022em; margin-bottom: 64px; max-width: 1000px; }}
.quote .accent-text {{ background: linear-gradient(120deg, #7C3AED 0%, #F472B6 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.attribution {{ display: flex; align-items: center; gap: 22px; margin-bottom: 48px; }}
.avatar {{ width: 96px; height: 96px; border-radius: 999px; background: #FAF8F5; display: block; box-shadow: 0 6px 20px rgba(124, 58, 237, 0.28); border: 3px solid #FFFFFF; outline: 3px solid #7C3AED; outline-offset: -6px; flex-shrink: 0; object-fit: cover; }}
.attribution-text .name {{ font-family: 'Poppins', sans-serif; font-weight: 600; font-size: 26px; color: #1E2030; line-height: 1.1; }}
.attribution-text .role {{ font-family: 'Inter', sans-serif; font-weight: 400; font-size: 18px; color: #64748B; margin-top: 4px; }}
.status-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 999px; background: #12B488; margin-right: 8px; box-shadow: 0 0 0 4px rgba(18, 180, 136, 0.2); vertical-align: middle; }}
.closer {{ background: #FFFFFF; border: 1px solid #EDE9FE; border-left: 4px solid #7C3AED; border-radius: 16px; padding: 22px 28px; font-family: 'Inter', sans-serif; font-weight: 400; font-size: 21px; line-height: 1.4; color: #334155; max-width: 980px; box-shadow: 0 8px 28px rgba(30, 32, 48, 0.05); }}
.closer strong {{ color: #1E2030; font-weight: 600; }}
.footer {{ position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; padding-top: 20px; margin-top: auto; border-top: 1px solid #E2E8F0; }}
.footer .hashtags {{ font-weight: 500; font-size: 14px; color: #64748B; }}
.footer .url {{ font-weight: 600; font-size: 14px; color: #7C3AED; }}
</style>
</head>
<body>
<div class="canvas">
    <svg class="deco-dots" viewBox="0 0 200 200" fill="none">
        <circle cx="50" cy="50" r="8" fill="#7C3AED" fill-opacity="0.3"/>
        <circle cx="100" cy="50" r="8" fill="#F472B6" fill-opacity="0.3"/>
        <circle cx="150" cy="50" r="8" fill="#12B488" fill-opacity="0.3"/>
        <circle cx="50" cy="100" r="8" fill="#F472B6" fill-opacity="0.3"/>
        <circle cx="100" cy="100" r="8" fill="#12B488" fill-opacity="0.3"/>
        <circle cx="150" cy="100" r="8" fill="#7C3AED" fill-opacity="0.3"/>
        <circle cx="50" cy="150" r="8" fill="#12B488" fill-opacity="0.3"/>
        <circle cx="100" cy="150" r="8" fill="#7C3AED" fill-opacity="0.3"/>
        <circle cx="150" cy="150" r="8" fill="#F472B6" fill-opacity="0.3"/>
    </svg>
    <div class="header">
        <img class="logo" src="file:///app/social_studio/static/social/taggiq/logo.png" alt="TaggIQ">
        <div class="tag">{tag}</div>
    </div>
    <div class="content">
        <div class="quote-mark">&ldquo;</div>
        <div class="quote">{quote_a} <span class="accent-text">{quote_b}</span></div>
        <div class="attribution">
            <img class="avatar" src="file:///app/social_studio/static/social/taggiq/prakash.jpg" alt="Prakash Inani">
            <div class="attribution-text">
                <div class="name">Prakash Inani</div>
                <div class="role"><span class="status-dot"></span>{attribution_role}</div>
            </div>
        </div>
        <div class="closer"><strong>{closer_strong}.</strong> {closer_body}</div>
    </div>
    <div class="footer">
        <div class="hashtags">{hashtags}</div>
        <div class="url">taggiq.com</div>
    </div>
</div>
</body>
</html>
'''


CARD_GRADIENT_TEMPLATE = '''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@font-face {{ font-family: 'Poppins'; font-weight: 700; src: url('file:///app/social_studio/static/social/taggiq/Poppins-Bold.ttf') format('truetype'); font-display: block; }}
@font-face {{ font-family: 'Poppins'; font-weight: 600; src: url('file:///app/social_studio/static/social/taggiq/Poppins-SemiBold.ttf') format('truetype'); font-display: block; }}
@font-face {{ font-family: 'Inter'; font-weight: 400; src: url('file:///app/social_studio/static/social/taggiq/Inter-Regular.ttf') format('truetype'); font-display: block; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1200px; height: 1200px; overflow: hidden; font-family: 'Inter', sans-serif; color: #1E2030; background: #FAF8F5; -webkit-font-smoothing: antialiased; }}
.canvas {{ width: 1200px; height: 1200px; display: flex; flex-direction: column; position: relative; background: #FAF8F5; }}
.header-band {{ position: relative; background: linear-gradient(135deg, #1E2030 0%, #4C1D95 55%, #7C3AED 100%); padding: 70px 80px 56px; overflow: hidden; }}
.header-band::before {{ content: ''; position: absolute; inset: 0; background-image: radial-gradient(circle, rgba(255, 255, 255, 0.07) 1.5px, transparent 1.5px); background-size: 28px 28px; pointer-events: none; }}
.header-band::after {{ content: ''; position: absolute; top: -120px; right: -120px; width: 480px; height: 480px; border-radius: 999px; background: radial-gradient(circle, rgba(244, 114, 182, 0.25) 0%, transparent 60%); pointer-events: none; }}
.header-top {{ position: relative; display: flex; align-items: center; justify-content: space-between; margin-bottom: 40px; z-index: 2; }}
.logo {{ height: 52px; filter: brightness(0) invert(1); }}
.tag {{ background: rgba(255, 255, 255, 0.12); color: #FFFFFF; padding: 10px 22px; border-radius: 999px; font-weight: 500; font-size: 13px; letter-spacing: 0.16em; text-transform: uppercase; border: 1px solid rgba(255, 255, 255, 0.18); }}
.kicker {{ position: relative; z-index: 2; display: inline-flex; align-items: center; gap: 10px; font-family: 'Inter', sans-serif; font-weight: 500; font-size: 15px; letter-spacing: 0.18em; text-transform: uppercase; color: #F472B6; margin-bottom: 14px; }}
.kicker::before {{ content: ''; width: 32px; height: 2px; background: #F472B6; display: inline-block; }}
.headline {{ position: relative; z-index: 2; font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 60px; line-height: 1.04; color: #FFFFFF; letter-spacing: -0.025em; max-width: 960px; }}
.headline .accent-text {{ background: linear-gradient(120deg, #F472B6 0%, #FBBF24 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.body-section {{ flex: 1; padding: 50px 80px 30px; display: flex; flex-direction: column; gap: 18px; position: relative; }}
.body-section::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-image: linear-gradient(rgba(30, 32, 48, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(30, 32, 48, 0.03) 1px, transparent 1px); background-size: 48px 48px; pointer-events: none; }}
.item {{ position: relative; display: flex; align-items: flex-start; gap: 24px; padding: 18px 24px; background: #FFFFFF; border-radius: 14px; border: 1px solid #E2E8F0; box-shadow: 0 2px 10px rgba(30, 32, 48, 0.035); z-index: 1; }}
.item:nth-child(1) {{ --sev: #F44336; }}
.item:nth-child(2) {{ --sev: #F59E0B; }}
.item:nth-child(3) {{ --sev: #1E88FF; }}
.item:nth-child(4) {{ --sev: #12B488; }}
.item:nth-child(5) {{ --sev: #A78BFA; }}
.item-num {{ flex-shrink: 0; width: 48px; height: 48px; border-radius: 12px; background: color-mix(in srgb, var(--sev) 14%, transparent); color: var(--sev); display: flex; align-items: center; justify-content: center; font-family: 'Poppins', sans-serif; font-weight: 700; font-size: 22px; }}
.item-body {{ flex: 1; }}
.item-title {{ font-family: 'Poppins', sans-serif; font-weight: 600; font-size: 22px; color: #1E2030; line-height: 1.2; margin-bottom: 4px; letter-spacing: -0.005em; }}
.item-desc {{ font-family: 'Inter', sans-serif; font-weight: 400; font-size: 16px; color: #64748B; line-height: 1.4; }}
.footer {{ display: flex; align-items: center; justify-content: space-between; padding: 20px 80px 28px; border-top: 1px solid #E2E8F0; background: #FAF8F5; position: relative; z-index: 2; }}
.footer .hashtags {{ font-weight: 500; font-size: 14px; color: #64748B; }}
.footer .url {{ font-weight: 600; font-size: 14px; color: #7C3AED; }}
</style>
</head>
<body>
<div class="canvas">
    <div class="header-band">
        <div class="header-top">
            <img class="logo" src="file:///app/social_studio/static/social/taggiq/logo.png" alt="TaggIQ">
            <div class="tag">{tag}</div>
        </div>
        <div class="kicker">{kicker}</div>
        <div class="headline">{headline_a} <span class="accent-text">{headline_b}</span></div>
    </div>
    <div class="body-section">
        {items_html}
    </div>
    <div class="footer">
        <div class="hashtags">{hashtags}</div>
        <div class="url">taggiq.com</div>
    </div>
</div>
</body>
</html>
'''


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

def _render_hero_dark(post, slots):
    steps_html = '\n        '.join(
        f'<div class="step"><div class="step-num">{i+1}</div>'
        f'<div class="step-text"><strong>{title}</strong>{desc}</div></div>'
        for i, (title, desc) in enumerate(slots['steps'])
    )
    return HERO_DARK_TEMPLATE.format(
        title=f'Post {post.post_number} - {slots["tag"]}',
        tag=slots['tag'],
        big_a=slots['big_a'],
        big_a_unit=slots['big_a_unit'],
        big_b=slots['big_b'],
        big_b_unit=slots['big_b_unit'],
        title_a=slots['title_a'],
        title_b=slots['title_b'],
        steps_html=steps_html,
        hashtags=slots['hashtags'],
    )


def _render_native_warm(post, slots):
    return NATIVE_WARM_TEMPLATE.format(
        title=f'Post {post.post_number} - Founder Note',
        tag=slots['tag'],
        quote_a=slots['quote_a'],
        quote_b=slots['quote_b'],
        attribution_role=slots['attribution_role'],
        closer_strong=slots['closer_strong'],
        closer_body=slots['closer_body'],
        hashtags=slots['hashtags'],
    )


def _render_card_gradient(post, slots):
    items_html = '\n        '.join(
        f'<div class="item"><div class="item-num">{num}</div>'
        f'<div class="item-body"><div class="item-title">{title}</div>'
        f'<div class="item-desc">{desc}</div></div></div>'
        for (num, title, desc) in slots['items']
    )
    return CARD_GRADIENT_TEMPLATE.format(
        title=f'Post {post.post_number} - {slots["tag"]}',
        tag=slots['tag'],
        kicker=slots['kicker'],
        headline_a=slots['headline_a'],
        headline_b=slots['headline_b'],
        items_html=items_html,
        hashtags=slots['hashtags'],
    )


RENDERERS = {
    TIER_HERO: _render_hero_dark,
    TIER_NATIVE: _render_native_warm,
    TIER_CARD: _render_card_gradient,
}


class Command(BaseCommand):
    help = 'Batch-author bespoke HTML for SocialPosts using three proven templates'

    def add_arguments(self, parser):
        parser.add_argument('--from', type=int, default=5, dest='start')
        parser.add_argument('--to', type=int, default=30, dest='end')
        parser.add_argument('--render', action='store_true', help='Also invoke render_post on each file')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        start = options['start']
        end = options['end']
        do_render = options['render']
        dry = options['dry_run']

        OUT_DIR.mkdir(parents=True, exist_ok=True)

        authored = 0
        rendered = 0
        skipped = []

        for n in range(start, end + 1):
            tier = TIER_MAP.get(n)
            slots = POST_SLOTS.get(n)
            if not tier or not slots:
                skipped.append(n)
                continue

            try:
                post = SocialPost.objects.get(post_number=n)
            except SocialPost.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  #{n}: SocialPost not found, skipping'))
                continue

            renderer = RENDERERS[tier]
            html = renderer(post, slots)

            out_file = OUT_DIR / f'post_{n:02d}.html'
            if dry:
                self.stdout.write(f'  [DRY] #{n} tier={tier} -> {out_file.name} ({len(html)} chars)')
                continue

            out_file.write_text(html)
            authored += 1

            # Also update bespoke_html_path on the post so render_post resolves it
            rel = out_file.relative_to(BASE_DIR)
            if post.bespoke_html_path != str(rel):
                post.bespoke_html_path = str(rel)
                post.save(update_fields=['bespoke_html_path', 'updated_at'])

            self.stdout.write(f'  #{n:2d} [{tier}] -> {out_file.name}')

            if do_render:
                try:
                    call_command('render_post', post_number=n, html=str(rel), verbosity=0)
                    rendered += 1
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f'     render failed: {exc}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Authored {authored} HTML files. Rendered {rendered} PNGs.'
        ))
        if skipped:
            self.stdout.write(self.style.WARNING(f'Skipped (no slots): {skipped}'))
