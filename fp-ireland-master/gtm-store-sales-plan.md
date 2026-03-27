# Fully Promoted Dublin — Store Sales GTM Plan
**Created:** 2026-03-27
**Owner:** Prakash Inani
**Goal:** Generate 15+ new customer conversations and EUR 5,000+ in new orders within 6 weeks

---

## Situation

Fully Promoted Dublin (Unit A20, Kingswood Business Park) sells branded apparel, promotional products, and print solutions to local businesses. Sales are below target. The store has a physical showroom but not enough businesses know it exists or have a reason to walk in.

**Current state:**
- BNI campaign: 235 prospects, 185 unsent, only 4 engaged
- No active outbound to non-BNI local businesses
- Google Maps scraper available but not yet used for FP Dublin
- No structured referral programme
- Limited local SEO/Google Business Profile activity

**What needs to change:** Shift from waiting for inbound to aggressive, targeted outbound across multiple channels simultaneously.

---

## Target Segments

### Segment 1: Construction & Trades
| Attribute | Detail |
|-----------|--------|
| Who | Construction companies, electricians, plumbers, builders |
| Decision maker | Owner or office manager |
| What they buy | Hi-vis vests, branded workwear, hard hat stickers, van magnets |
| Order size | EUR 300-1,500 |
| Frequency | Ongoing (new hires, replacements, new projects) |
| Pain point | Staff on site with no branding looks unprofessional to clients |
| Buying trigger | New project, new hires, client-facing site work |
| Geography | Dublin, Kildare, Wicklow |

**Outreach angle:** "Your lads are on site every day — that's hundreds of impressions. Branded workwear makes you look established and wins trust with clients before you say a word."

### Segment 2: Hotels & Hospitality
| Attribute | Detail |
|-----------|--------|
| Who | Hotels, restaurants, cafes, pubs with staff |
| Decision maker | General manager or owner |
| What they buy | Staff uniforms (polos, aprons, shirts), branded menus, table tents |
| Order size | EUR 1,000-5,000 |
| Frequency | 1-2x/year (seasonal refresh, new hires) |
| Pain point | Staff look inconsistent, uniforms wear out, hard to find local supplier who stocks hospitality-grade fabrics |
| Buying trigger | New season, staff turnover, refurbishment, new opening |
| Geography | Dublin city centre, Dublin suburbs |

**Outreach angle:** "First impressions in hospitality are everything. We supply staff uniforms that look sharp and last — and we're local, so reorders take days, not weeks."

### Segment 3: Sports Clubs & GAA
| Attribute | Detail |
|-----------|--------|
| Who | GAA clubs, soccer clubs, rugby clubs, gyms, fitness studios |
| Decision maker | Club secretary, committee member, or gym owner |
| What they buy | Jerseys, training tops, club merchandise (hoodies, beanies, bags) |
| Order size | EUR 500-3,000 |
| Frequency | Seasonal (pre-season orders) + events |
| Pain point | Online suppliers are slow, minimum order quantities are high, can't see/feel the product before ordering |
| Buying trigger | New season, tournament, fundraiser, club anniversary |
| Geography | Dublin, Kildare, Wicklow, Meath |

**Outreach angle:** "New season coming up? We can kit out your club in 2 weeks. Pop into our showroom in Kingswood and see the gear in person before you commit."

### Segment 4: Schools & Colleges
| Attribute | Detail |
|-----------|--------|
| Who | Secondary schools, primary schools, colleges, creches |
| Decision maker | Principal, school secretary, or parent association |
| What they buy | School uniforms, PE kits, graduation hoodies, event t-shirts |
| Order size | EUR 1,000-5,000 |
| Frequency | Seasonal (Aug-Sep peak, Jan for spring term) |
| Pain point | Current supplier is slow or expensive, parents complain about quality |
| Buying trigger | Back-to-school season, graduation, school event, switching suppliers |
| Geography | South Dublin, Kildare, West Dublin |

**Outreach angle:** "We supply school uniforms and PE kits locally. Parents can visit our showroom, try sizes, and collect orders — no waiting for postal deliveries."

### Segment 5: Professional Services (Accountants, Solicitors, Financial)
| Attribute | Detail |
|-----------|--------|
| Who | Accounting firms, law firms, insurance brokers, financial advisors |
| Decision maker | Office manager or partner |
| What they buy | Business cards, branded notebooks, client gift packs, staff polo shirts |
| Order size | EUR 200-800 |
| Frequency | Quarterly (client gifts, new starters) |
| Pain point | Want to look polished for clients but don't have time to source branded items |
| Buying trigger | Christmas gifting, client events, new office, new hires |
| Geography | Dublin (especially business parks near Kingswood) |

**Outreach angle:** "Your clients judge you by the details. A branded welcome pack or a quality corporate gift costs less than you'd think and makes a lasting impression."

---

## Channel Plan

### Channel 1: Google Maps Scraper → Email Outreach
**Priority: HIGH | Timeline: Week 1-2**

Use `google-maps-scraper/` to build targeted prospect lists, then run segment-specific email sequences via the outreach system.

#### Step-by-step:

**Step 1: Configure scraper for each segment**

Run these searches (50-100 results each):

| Segment | Search queries |
|---------|---------------|
| Construction | "construction companies Dublin", "builders Dublin", "electricians Dublin", "plumbers Dublin Kildare" |
| Hotels | "hotels Dublin", "restaurants Dublin", "cafes Dublin south", "pubs Dublin" |
| Sports | "GAA clubs Dublin", "soccer clubs Dublin", "rugby clubs Dublin Kildare", "gyms Dublin", "fitness studios Dublin" |
| Schools | "secondary schools Dublin south", "primary schools Kildare", "schools Tallaght", "schools Clondalkin" |
| Professional | "accountants Dublin", "solicitors Dublin", "financial advisors Dublin" |

**Step 2: Import scraped prospects into FP Dublin BNI campaign (or create a new campaign)**

Create a new campaign `FP Dublin Local Outreach` to keep these separate from BNI prospects:

```bash
venv/bin/python manage.py shell -c "
from campaigns.models import Campaign
c = Campaign.objects.create(
    name='FP Dublin Local Outreach',
    product='fullypromoted',
    from_name='Prakash Inani',
    from_email='prakash@fullypromoted.ie',
    sending_enabled=True,
    max_emails_per_day=50,
)
print(f'Created: {c.name} ({c.id})')
"
```

**Step 3: Write segment-specific email sequences**

Each segment gets a 3-email sequence:
- Email 1 (Day 0): Segment-specific hook + soft CTA
- Email 2 (Day 5): Different angle or seasonal hook
- Email 3 (Day 12): Breakup — graceful close

See "Email Templates by Segment" section below.

**Step 4: Send in batches**

- 20-30 emails per segment per day
- Start with Construction (highest volume, most urgent need)
- Add Hotels and Sports in week 2
- Schools and Professional in week 3

**Expected results:**
| Metric | Target |
|--------|--------|
| Prospects scraped | 300-400 |
| Emails sent (Seq 1) | 300 |
| Reply rate | 5-8% |
| Conversations started | 15-25 |
| Orders from outreach | 5-8 |
| Revenue | EUR 2,500-5,000 |

---

### Channel 2: BNI Network — Send Seq 1 to 185 Unsent
**Priority: HIGH | Timeline: Week 1**

#### Step-by-step:

**Step 1: Review the BNI send script**
```bash
cat fp-ireland-master/send_bni_promo.py
```

**Step 2: Dry run to verify eligible count**
```bash
python3 fp-ireland-master/send_bni_promo.py --seq 1 --dry-run
```

**Step 3: Send to all 185**
```bash
python3 fp-ireland-master/send_bni_promo.py --seq 1 --max 185
```

**Step 4: Monitor replies with cron job**

The `/fp-email-expert` cron is already running every 5 min. It will pick up BNI replies automatically.

**Expected results:**
| Metric | Target |
|--------|--------|
| Emails sent | 185 |
| Reply rate | 8-12% (BNI members are warmer) |
| Conversations | 15-20 |
| Referrals generated | 5-10 |
| Orders | 3-5 |

---

### Channel 3: Door-to-Door — Business Park Walks
**Priority: HIGH | Timeline: Ongoing, starting Week 1**

#### Step-by-step:

**Step 1: Prepare a "walk kit"**
- 5-6 sample products (branded polo, mug, notebook, pen, hi-vis vest, tote bag)
- Business cards (50+)
- Simple one-page flyer: "Fully Promoted — Your Local Branded Products Partner" with QR code to website
- Notepad to capture names, emails, and what they're interested in

**Step 2: Map the routes**

| Week | Location | Estimated businesses |
|------|----------|---------------------|
| Week 1 (Mon) | Kingswood Business Park | 30-40 |
| Week 1 (Wed) | Citywest Business Campus | 50-60 |
| Week 2 (Mon) | Park West Business Park | 40-50 |
| Week 2 (Wed) | Ballymount Industrial Estate | 40-50 |
| Week 3 (Mon) | Sandyford Business District | 50-60 |
| Week 3 (Wed) | Tallaght Business Park | 30-40 |

**Step 3: The 60-second pitch**

Walk in, ask for the person who handles ordering supplies or uniforms:

> "Hi, I'm Prakash from Fully Promoted, just around the corner in Kingswood. We do branded gear — uniforms, corporate gifts, promotional stuff. Just wanted to drop in and say hello. Here's a sample of what we do [hand them a branded item]. If you ever need anything, we're literally 5 minutes away."

**Step 4: Follow up by email within 48 hours**

Add every contact to the outreach system. Send a short personal email:

> "Great meeting you at [company] on [day]. If you ever need branded gear for the team, I'm right here in Kingswood. Here's our website: fullypromoted.ie"

**Step 5: Track results**

Log every visit in a simple spreadsheet or add to the outreach DB:
- Company name, contact name, email, phone
- What they were interested in (or "not now")
- Follow-up date

**Expected results:**
| Metric | Target |
|--------|--------|
| Businesses visited per week | 20 |
| Business cards collected | 8-10 per week |
| Follow-up emails sent | 8-10 per week |
| Conversations that turn into quotes | 2-3 per week |
| Orders per month | 4-6 |
| Revenue per month | EUR 2,000-4,000 |

---

### Channel 4: Google Business Profile Optimisation
**Priority: MEDIUM | Timeline: Week 1 (one-time setup, then ongoing)**

#### Step-by-step:

**Step 1: Audit current profile**
- Go to business.google.com
- Check: photos, business hours, services listed, description, categories

**Step 2: Optimise the profile**

- **Business name:** Fully Promoted Dublin — Branded Apparel & Promotional Products
- **Primary category:** Promotional Products Supplier
- **Additional categories:** Screen Printing Shop, Embroidery Shop, Corporate Gift Supplier, Uniform Supply Service
- **Description:** Include keywords naturally:
  > "Fully Promoted Dublin is your local one-stop shop for branded apparel, promotional products, and print solutions. Based at Unit A20, Kingswood Business Park, we supply custom uniforms, corporate gifts, event merchandise, and marketing materials to businesses across Dublin and beyond. Part of the world's largest promotional products franchise with 300+ locations worldwide. Visit our showroom to see and touch products before you order."
- **Photos:** Upload 10-15 photos:
  - Showroom interior (3-4 angles)
  - Sample products close-up
  - Finished orders (with customer permission)
  - Prakash at the counter / with products
  - Store exterior / signage
- **Services:** List every service individually:
  - Custom branded apparel
  - Corporate uniforms
  - Promotional products
  - Business cards and stationery
  - Corporate gift packs
  - Event merchandise
  - Trade show supplies
  - School uniforms
  - Sports team kits
  - Hi-vis and workwear

**Step 3: Start posting weekly**

Google Posts appear on your Business Profile and help with local SEO:

| Week | Post topic |
|------|-----------|
| 1 | "New in: summer polo range. Visit our showroom to see colours and feel the fabric." |
| 2 | Photo of a finished order: "Just delivered 50 branded polos to [company type]." |
| 3 | "Getting ready for a trade show? We can kit you out in under 2 weeks." |
| 4 | "Did you know we do corporate gift packs? Perfect for client appreciation." |

**Step 4: Ask for reviews**

After every completed order, send a quick email:
> "Thanks again for the order! If you have a moment, a Google review would really help us out: [direct review link]"

Target: 2 reviews per month. Within 6 months you'll have 12+ reviews, which dramatically improves map ranking.

**Expected results:**
| Metric | Target (6 months) |
|--------|-------------------|
| Google Business Profile views | 500+/month |
| Direction requests | 20+/month |
| Phone calls from Google | 10+/month |
| Website clicks | 30+/month |

---

### Channel 5: Customer Referral Programme
**Priority: MEDIUM | Timeline: Week 2**

#### Step-by-step:

**Step 1: Define the offer**

> **Refer & Save:** Know a business that needs branded gear? Refer them to us. When they place their first order, you get EUR 50 credit on your next order.

**Step 2: Email all existing customers**

Send a simple, personal email to every past customer:

> Subject: Quick favour?
>
> Hi [Name],
>
> Hope the [last product they ordered] is working well for you.
>
> Quick one — if you know any other businesses that might need branded gear, uniforms, or promotional products, I'd really appreciate the introduction. As a thank you, I'll give you EUR 50 off your next order for every referral that turns into a customer.
>
> No pressure at all, just thought I'd mention it. You know where to find me!
>
> Cheers,
> Prakash

**Step 3: Remind at point of sale**

Every time you deliver an order or have a customer in the showroom, mention the referral programme. Have small cards printed:

> "Know someone who needs branded gear? Refer them and get EUR 50 off your next order."

**Step 4: Track referrals**

Simple spreadsheet:
- Referrer name
- Referred business
- Date referred
- Order placed? Y/N
- Credit issued? Y/N

**Expected results:**
| Metric | Target (per month) |
|--------|-------------------|
| Referral emails sent | All past customers (one-time) |
| Referrals received | 3-5 per month |
| Referrals converting | 1-2 per month |
| Revenue from referrals | EUR 500-1,500/month |

---

## Email Templates by Segment

### Construction — Email 1

**Subject A:** "branded workwear for your crew?"
**Subject B:** "quick question about your site gear"

```
Hi {{FNAME}},

Prakash here from Fully Promoted Dublin. We're based in Kingswood Business Park and we supply branded workwear to construction and trade companies across Dublin.

If your crew is on site without branded gear, you're missing an easy win. Every job site is a billboard for your business, and branded hi-vis, jackets, and polos make you look established to clients.

We can turn it around in under 2 weeks. Worth a quick look? Pop into our showroom or I can drop samples to you.

Cheers,
Prakash Inani
Fully Promoted Dublin
Unit A20, Kingswood Business Park
fullypromoted.ie
```

### Hotels & Hospitality — Email 1

**Subject A:** "staff uniforms that last"
**Subject B:** "quick thought for {{COMPANY}}"

```
Hi {{FNAME}},

Prakash here from Fully Promoted Dublin. We supply staff uniforms to hotels, restaurants, and cafes across Dublin.

First impressions in hospitality are everything, and your team's look is a big part of that. We carry hospitality-grade polos, shirts, and aprons that actually hold up through commercial washing.

The nice thing is we're local in Kingswood, so reorders take days, not weeks. And you can see and feel everything in our showroom before committing.

Worth a chat if you're due a refresh?

Cheers,
Prakash Inani
Fully Promoted Dublin
Unit A20, Kingswood Business Park
fullypromoted.ie
```

### Sports Clubs — Email 1

**Subject A:** "new season gear for {{COMPANY}}?"
**Subject B:** "quick one about your club kit"

```
Hi {{FNAME}},

Prakash here from Fully Promoted Dublin. We supply jerseys, training gear, and club merchandise to sports clubs across Dublin and Kildare.

If your club is gearing up for a new season, we can get you sorted in about 2 weeks. The difference with us is you can visit our showroom in Kingswood, see the gear in person, and pick exactly what works for your club.

No massive minimum orders either. Happy to chat if it's useful.

Cheers,
Prakash Inani
Fully Promoted Dublin
Unit A20, Kingswood Business Park
fullypromoted.ie
```

### Professional Services — Email 1

**Subject A:** "quick thought for {{COMPANY}}"
**Subject B:** "branded welcome packs?"

```
Hi {{FNAME}},

Prakash here from Fully Promoted Dublin. We help professional firms look polished with branded items: business cards, notebooks, client gift packs, and team gear.

A quality branded welcome pack for new clients costs less than you'd think and makes a real impression. We can put one together for you to see.

We're right here in Kingswood if you'd like to pop in, or I'm happy to bring samples to you.

Cheers,
Prakash Inani
Fully Promoted Dublin
Unit A20, Kingswood Business Park
fullypromoted.ie
```

---

## 6-Week Execution Timeline

| Week | Action | Owner | Target |
|------|--------|-------|--------|
| **Week 1** | Send BNI Seq 1 to 185 unsent prospects | Claude/Prakash | 185 emails |
| **Week 1** | Scrape Construction + Hotels from Google Maps | Claude | 100-150 prospects |
| **Week 1** | Walk Kingswood + Citywest business parks | Prakash | 20 visits |
| **Week 1** | Optimise Google Business Profile | Prakash | Complete |
| **Week 2** | Send Construction segment outreach (Seq 1) | Claude | 50-75 emails |
| **Week 2** | Send Hotels segment outreach (Seq 1) | Claude | 50-75 emails |
| **Week 2** | Walk Park West + Ballymount | Prakash | 20 visits |
| **Week 2** | Launch referral programme email to past customers | Claude | All past customers |
| **Week 3** | Scrape Sports Clubs + Schools + Professional | Claude | 150-200 prospects |
| **Week 3** | Send Sports + Professional outreach (Seq 1) | Claude | 100 emails |
| **Week 3** | Walk Sandyford + Tallaght | Prakash | 20 visits |
| **Week 3** | Follow up on all door-to-door contacts | Claude | 20-30 follow-ups |
| **Week 4** | Send Seq 2 follow-ups to all segments | Claude | 200+ emails |
| **Week 4** | Continue business park walks (repeat high-potential areas) | Prakash | 20 visits |
| **Week 4** | First Google Business Profile review push | Prakash | Ask 5 customers |
| **Week 5** | Send Seq 3 (breakup) to non-responders | Claude | 150+ emails |
| **Week 5** | Schools outreach (timing for Sep planning) | Claude | 50 emails |
| **Week 5** | Review results, double down on best segment | Both | Analysis |
| **Week 6** | Scale winning segment, pause losing ones | Both | Optimise |

---

## Success Metrics — 6-Week Targets

| Metric | Target |
|--------|--------|
| Total prospects contacted (all channels) | 500+ |
| Conversations started | 30-40 |
| Showroom visits | 10-15 |
| Quotes sent | 15-20 |
| Orders placed | 8-12 |
| Revenue generated | EUR 5,000-10,000 |
| Google reviews collected | 4-6 |
| Referrals received | 5-8 |

---

## Budget

| Item | Cost |
|------|------|
| Google Maps API (scraping) | EUR 10-20 |
| Email sending (Zoho/SES) | Existing infrastructure |
| Sample products for door-to-door | EUR 100-200 (use existing stock) |
| Printed flyers/cards | EUR 50-100 |
| Referral credits | EUR 50 per successful referral (only paid on conversion) |
| **Total upfront cost** | **EUR 160-320** |

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Low email reply rates | Test subject lines A/B, adjust messaging per segment, keep emails under 100 words |
| Door-to-door feels awkward | Bring samples — having something tangible to hand over makes the conversation natural |
| Google Maps scraper returns bad data | Manually verify top 20 prospects per segment before sending |
| Too many channels at once | Start with BNI + Construction outreach + 1 business park walk. Add channels as you find rhythm |
| Seasonal timing wrong for some segments | Schools = plan in May for Sep delivery. Sports = target now for summer season. Hotels = always relevant |
