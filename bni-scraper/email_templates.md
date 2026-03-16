# BNI TaggIQ Email Sequence
# Merge fields: {{FNAME}}, {{COMPANY}}, {{CITY}}, {{SEGMENT}}
# Sequence: Peer -> Curiosity -> Design Partner -> Social Proof -> Breakup
# Timing: Day 0, Day 5, Day 10, Day 15, Day 21
# Psychology: Relationship-first, insight-second, invitation-third

---

## EMAIL 1: Peer Story (Day 0)

**Subject A/B test:**
- A: "Fellow BNI member in print and promo"
- B: "{{FNAME}}, quick one from a fellow BNI member"

---

Hi {{FNAME}},

Hope you're well. I came across your profile on BNI Connect and noticed we're both in the print and promo space, so I thought I'd say hello.

I run a print and promo shop in Dublin, and one thing that always drove me mad was having everything in different places. Quotes in one tool, artwork approvals over email, purchase orders somewhere else, and then re-entering everything into Xero at the end. The same order getting typed four different times.

In the end, I built something to solve it for our own shop. It's called [TaggIQ](https://taggiq.com/) and it connects the whole journey from quote to invoice in one place, built specifically for how print and promo businesses actually work.

I'd be really interested to hear how you're managing this at {{COMPANY}}. Always great to learn how other BNI members in the industry handle their workflow.

If you're curious, I'd be happy to share what we built. No pressure at all.

Best regards,
Prakash Inani
Founder, [TaggIQ](https://taggiq.com/)
Kingswood Business Park, Dublin

---


## EMAIL 2: Curiosity (Day 5 -only if no reply)

**Subject A/B test:**
- A: "Quick question for fellow BNI print shops"
- B: "{{FNAME}}, curious how other BNI members handle this"

---

Hi {{FNAME}},

I've been chatting with a few BNI members in the print and promo space over the past couple of weeks. It's been eye-opening how differently everyone runs things -spreadsheets, Xero workarounds, DecoNetwork, even WhatsApp threads for artwork approvals.

One thing that keeps coming up: a customer approves a quote three weeks later, and the team has to go hunting for supplier pricing all over again because nothing was saved in one place.

Does that happen in your business, or have you found a way around it?

I'm also trying to connect a small group of print and promo owners inside BNI who are interested in sharing best practices. If that sounds useful, happy to loop you in.

Best regards,
Prakash Inani
Founder, [TaggIQ](https://taggiq.com/)
Kingswood Business Park, Dublin

---


## EMAIL 3: Design Partner Invitation (Day 10 -only if no reply)

**Subject A/B test:**
- A: "Small group forming -curious if you'd be interested"
- B: "Looking for a few industry partners"

---

Hi {{FNAME}},

After speaking with a number of BNI members in print and promo, the same operational pain points keep surfacing -quoting takes too long, artwork approvals get lost in email, and supplier orders end up being re-entered into accounting manually.

Because of that, I'm putting together a small group of design partners -five businesses in the industry who want to help shape what we're building at TaggIQ.

What that looks like:
- You tell us what slows your team down
- We build features around your actual workflow
- You get early access and founding-partner pricing (40% off the first year)

I'm keeping this to five businesses so we can give each one proper attention. Two spots are already taken.

If that sounds interesting, I'd love to show you what we've built so far and hear how your team currently works. Happy to jump on a quick 15-minute call whenever suits.

Best regards,
Prakash Inani
Founder, [TaggIQ](https://taggiq.com/)
Kingswood Business Park, Dublin

---


## EMAIL 4: Social Proof + Soft Close (Day 15 -only if no reply)

**Subject A/B test:**
- A: "Something I keep hearing from print shops"
- B: "Interesting pattern from BNI promo businesses"

---

Hi {{FNAME}},

Something interesting has come up in conversations with print and promo businesses over the past few weeks.

Several teams told me they spend anywhere from 30 minutes to an hour per order re-entering the same information -moving from quotes to artwork approvals to supplier orders and then copying it all into Xero or QuickBooks.

A few early partners are now running that entire flow through TaggIQ. One team told me their quote-to-invoice process went from touching four different tools to one screen.

If you're ever curious to see how it works, I'm happy to give you a quick walkthrough -no commitment, just 15 minutes.

Either way, always great connecting with fellow BNI members in the industry.

Best regards,
Prakash Inani
Founder, [TaggIQ](https://taggiq.com/)
Kingswood Business Park, Dublin

---


## EMAIL 5: Breakup (Day 21 -only if no reply)

**Subject:**
- "Should I stop reaching out?"

---

Hi {{FNAME}},

I've sent a few messages and I know how busy things get running a business, so I wanted to check -is this something you'd like to hear more about, or would you prefer I stop reaching out?

Either way is completely fine. Just didn't want to keep landing in your inbox if it's not relevant.

Best regards,
Prakash Inani
Founder, [TaggIQ](https://taggiq.com/)
Kingswood Business Park, Dublin

---

# DESIGN NOTES

## Why this sequence works (BNI psychology):

1. **Email 1 -Peer Story**: Positions you as "one of them". Asks a question to invite reply. Mentions product only after establishing common ground.
2. **Email 2 -Curiosity**: No pitch. Starts a conversation about a shared pain point. Plants the community-building seed ("small group of BNI owners sharing best practices").
3. **Email 3 -Design Partner**: Highest-converting email. BNI members love helping other members build things. Scarcity ("five businesses, two spots taken") creates urgency without pressure.
4. **Email 4 -Social Proof**: Quantifies the pain (30-60 min per order). Shows real results (four tools to one screen). Soft demo offer with "no commitment, just 15 minutes".
5. **Email 5 -Breakup**: "Should I stop?" subject line has highest open rate of any cold email pattern. Giving permission to say no paradoxically increases positive replies.

## Key principles:
- Each email is under 150 words
- No bullet-point feature lists (except Email 3 which uses them for the offer)
- Reads like a real person wrote it
- BNI connection referenced in every email -it's the trust signal
- Each email has ONE idea, not five
- Subject lines are conversational, not marketing-y
- Send Tuesday-Thursday, 7-9 AM before their day gets busy
- If they reply to any email, STOP the sequence and switch to personal conversation

## A/B Testing Strategy:
- Variant A: Generic/curiosity-driven subject
- Variant B: Personalized with {{FNAME}} or direct
- Track reply rates per variant per sequence to optimize

## Merge Fields:
- `{{FNAME}}` -First name of decision maker
- `{{COMPANY}}` -Business name
- `{{CITY}}` -City (for future geo-personalization)
- `{{SEGMENT}}` -Business segment (for future segment-specific content)

## Campaign Safeguards:
- max_emails_per_prospect: 5 (covers full sequence)
- follow_up_days: 5 (gap between sequences)
- require_sequence_order: true (must send seq N before N+1)
- Only send to status=contacted (replied/engaged prospects get personal follow-up)
- Suppression list checked before every send
