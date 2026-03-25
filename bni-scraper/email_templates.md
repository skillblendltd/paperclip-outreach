# BNI TaggIQ Email Sequence v2
# Merge fields: {{FNAME}}, {{COMPANY}}, {{CITY}}, {{SEGMENT}}
# Sequence: Conversation Starter -> Shared Pain -> Invitation -> Social Proof -> Breakup
# Timing: Day 0, Day 7, Day 16, Day 28, Day 42
# Psychology: Question-first, relationship-second, product-third
# Every email under 100 words. No pitch in Email 1. Product introduced gradually.

---

## EMAIL 1: Conversation Starter (Day 0)

**Goal:** Get a reply. That's it. No pitch, no product mention.

**Subject A/B test:**
- A: "quick question about {{COMPANY}}"
- B: "{{FNAME}}, how do you handle artwork approvals?"

---

Hi {{FNAME}},

Spotted you on BNI Connect, looks like we're both in the print and promo world.

Quick question: how does your team handle artwork approvals? I've talked to a bunch of BNI members recently and it's wild how many are still chasing approvals over email and WhatsApp.

Curious if you've found something that works or if it's still a pain.

Cheers,
Prakash

---

**Word count:** ~60
**Why it works:** One specific question they can answer in one sentence. No product mention. Feels like a peer asking for advice, not a founder selling software.


## EMAIL 2: Shared Pain (Day 7, only if no reply)

**Goal:** Share what you learned, introduce what you built naturally.

**Subject A/B test:**
- A: "the artwork approval problem"
- B: "{{FNAME}}, thought you'd find this interesting"

---

Hi {{FNAME}},

Thought you might find this interesting. I asked about 20 BNI members in print and promo how they handle artwork approvals and order tracking. Almost everyone said some version of "email back and forth until someone finally says yes."

I actually built a tool to fix this for my own shop in Dublin. It's called [TaggIQ](https://taggiq.com/) and it connects quotes, approvals, orders and invoicing in one place. I'm also putting together a small group of BNI promo owners to share best practices on workflow.

Happy to share what I learned if you're dealing with the same thing.

Either way, no worries.

Prakash

---

**Word count:** ~80
**Why it works:** TaggIQ introduced as "a tool I built" not "our platform." Shares insight from real conversations. Low-pressure CTA.


## EMAIL 3: The Honest Builder (Day 16, only if no reply)

**Goal:** Lead with the builder story. Ask for feedback, not a sale. Offer free trial as BNI perk.

**Subject A/B test:**
- A: "built this for my own shop, curious what you'd think"
- B: "{{FNAME}}, quick favour to ask"

---

Hi {{FNAME}},

Reaching out again as a fellow BNI member in print and promo. I spent about 20 years building software products (including Toast, the restaurant POS) before starting my own promo shop in Dublin. When I saw how many of us still run on spreadsheets, email threads and manual invoicing, I knew I had to do something about it.

That's how [TaggIQ](https://taggiq.com/) came about, a POS platform built specifically for print and promo. Quotes, artwork approvals, orders, invoicing, one place.

I'd genuinely love your feedback. Worth a 15-minute look? As a fellow BNI member, happy to give you 3 months free to try it. No card, no commitment.

If you prefer to explore on your own first, you can sign up for a free trial at [taggiq.com](https://taggiq.com/signup). Just let me know which suppliers you work with and I'll make sure their catalog is loaded for you.

Prakash

---

**Word count:** ~120
**Why it works:** Broadens pain hook beyond artwork approvals. Toast credibility signals real software, not a side project. The ask is "give me feedback" not "buy my product." BNI free trial feels earned. Self-trial option catches people who won't book a call, and asking about suppliers gets engagement + intel.


## EMAIL 4: Real Pain, Real Fix (Day 28, only if no reply)

**Goal:** Mirror the exact language prospects use. Make the pain vivid, the fix simple.

**Subject A/B test:**
- A: "from email chaos to one screen"
- B: "{{FNAME}}, the artwork approval thing"

---

Hi {{FNAME}},

One thing I keep hearing from BNI members in promo: artwork approvals over email are a nightmare. Clients forget to reply, things slip through the cracks, and you end up chasing instead of selling.

That's exactly why I built [TaggIQ](https://taggiq.com/). One place for quotes, approvals, orders and invoicing. No more digging through inboxes.

If you're curious, happy to show you in 15 minutes. If not, no worries at all, always good to be connected through BNI.

Prakash

---

**Word count:** ~80
**Why it works:** Uses real language from prospect conversations ("things slip through the cracks", "email chaos"). Specific and relatable. Single CTA. Warm BNI close whether interested or not.


## EMAIL 5: Breakup (Day 42, only if no reply)

**Goal:** Permission-based close. Give them an easy out, which paradoxically increases replies.

**Subject A/B test:**
- A: "should I stop reaching out?"
- B: "{{FNAME}}, one last one"

---

Hi {{FNAME}},

I know how busy things get running a shop, so I'll keep this short.

If streamlining artwork approvals and quoting is ever on your radar, I'm always happy to chat. If not, completely understand.

Either way, wishing you well with the business.

Prakash

---

**Word count:** ~45
**Why it works:** Shortest email in the sequence. Names the specific pain instead of generic "workflow." Warm close. Respects their time.

---

# DESIGN NOTES

## What changed in v2:

1. **Email 1 has zero product mention.** Its only job is to start a conversation about a shared pain (artwork approvals). This is the biggest change.
2. **Every email is under 100 words.** The old sequence had emails at 150+. Mobile readers scan, they don't read paragraphs.
3. **Sign-off is "Prakash" not "Best regards, Prakash Inani, Founder, TaggIQ..."** The full signature felt corporate. A first-name sign-off feels like a peer. Full signature in replies only.
4. **Timing is slower: Day 0, 7, 16, 28, 42** instead of 0, 5, 10, 15, 21. BNI is relationship-based, 5 emails in 3 weeks felt pushy. 6 weeks feels patient.
5. **Subject lines are specific and curious** not generic. "how do you handle artwork approvals?" beats "Fellow BNI member in print and promo."
6. **Product is introduced gradually:** Email 1 (no mention) -> Email 2 ("I built a tool") -> Email 3 (named, with offer) -> Email 4 (results) -> Email 5 (breakup).

## Key principles:
- Each email under 100 words
- No bullet-point feature lists
- Reads like a text from a friend, not a newsletter
- BNI connection referenced naturally, not forced
- Each email has ONE ask
- Subject lines create curiosity, not announce a pitch
- Send Tuesday-Thursday, 7-9 AM local time
- If they reply to any email, STOP the sequence and switch to personal conversation

## A/B Testing Strategy:
- Variant A: Curiosity/outcome-driven subject
- Variant B: Personalized with {{FNAME}} or direct question
- Track reply rates per variant per sequence to optimize

## Merge Fields:
- `{{FNAME}}` - First name of decision maker
- `{{COMPANY}}` - Business name
- `{{CITY}}` - City (for future geo-personalization)
- `{{SEGMENT}}` - Business segment (for future segment-specific content)

## Campaign Safeguards:
- max_emails_per_prospect: 5 (covers full sequence)
- follow_up_days: 7 (minimum gap between sequences)
- require_sequence_order: true (must send seq N before N+1)
- Only send to status=contacted (replied/engaged prospects get personal follow-up)
- Suppression list checked before every send
