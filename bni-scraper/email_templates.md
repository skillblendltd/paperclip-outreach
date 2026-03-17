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

I actually built a tool to fix this for my own shop in Dublin. It connects quotes, approvals, orders and invoicing in one place. Happy to share what I learned if you're dealing with the same thing.

Either way, no worries.

Prakash

---

**Word count:** ~80
**Why it works:** TaggIQ introduced as "a tool I built" not "our platform." Shares insight from real conversations. Low-pressure CTA.


## EMAIL 3: Design Partner Invitation (Day 16, only if no reply)

**Goal:** Make them feel valued. Invite them to shape the product.

**Subject A/B test:**
- A: "would you want input on this?"
- B: "looking for 5 BNI members to help shape this"

---

Hi {{FNAME}},

I'm building a system specifically for print and promo shops, quotes, artwork approvals, orders, invoicing, all in one place. It's called [TaggIQ](https://taggiq.com/).

I'm looking for 5 BNI members to be design partners: tell me what slows your team down, and I'll build around your workflow. Partners get 40% off year one.

2 spots taken. Worth a 15-min chat?

Prakash

---

**Word count:** ~70
**Why it works:** Clear offer, clear scarcity, clear ask. BNI members love helping other members build things. The ask is tiny (15 min).


## EMAIL 4: Social Proof (Day 28, only if no reply)

**Goal:** Show real results from real shops. Make them curious enough to look.

**Subject A/B test:**
- A: "from 4 tools to 1 screen"
- B: "{{FNAME}}, quick update from BNI print shops"

---

Hi {{FNAME}},

Quick update. A few print and promo shops in BNI started using [TaggIQ](https://taggiq.com/) over the past month.

One team told me they went from using four different tools per order to one screen, quote to invoice. Another said artwork approvals that used to take days over email now close in hours.

If you're ever curious, happy to show you in 15 minutes. No pitch, just a walkthrough.

Either way, always great being connected through BNI.

Prakash

---

**Word count:** ~80
**Why it works:** Specific results (4 tools to 1, days to hours). "No pitch, just a walkthrough" removes pressure. Warm BNI close.


## EMAIL 5: Breakup (Day 42, only if no reply)

**Goal:** Permission-based close. Give them an easy out, which paradoxically increases replies.

**Subject A/B test:**
- A: "should I stop reaching out?"
- B: "{{FNAME}}, one last one"

---

Hi {{FNAME}},

I know how busy things get running a shop, so I'll keep this short.

Is streamlining your workflow something you'd want to explore, or would you prefer I stop reaching out? Either way is completely fine.

Prakash

---

**Word count:** ~40
**Why it works:** Shortest email in the sequence. Respects their time. "Either way is completely fine" gives permission to say no, which paradoxically gets more yes replies.

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
