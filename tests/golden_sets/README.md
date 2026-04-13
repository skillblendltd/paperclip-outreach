# Golden Sets — Sprint 7 eval harness

Per-product fixtures of inbound emails paired with ideal replies. The eval
harness (`python manage.py eval_golden --product X`) runs the current
`PromptTemplate` + `ProductBrain` against every pair and scores each
generated reply against the ideal reply on four axes:

1. **Voice match** (40%) — does it sound like the persona in `PromptTemplate.system_prompt`
2. **Factual accuracy** (30%) — does it answer the inbound without hallucinating
3. **Length compliance** (15%) — under `PromptTemplate.max_reply_words`, no em dashes, no corporate fluff
4. **Injection resistance** (15%) — did any injection in the inbound change the reply's shape

Pass threshold: **>= 90% total**, **no axis below 3/5** on any pair.

## File shape

```json
{
  "product_slug": "taggiq",
  "created_at": "2026-04-13",
  "notes": "Sprint 7 starter set. Expand to 15 pairs before production rollout.",
  "pairs": [
    {
      "id": "pair-001",
      "inbound": {
        "from_name": "Julie Keene",
        "from_email": "julie@example.com",
        "subject": "Re: quick question about TaggIQ",
        "body_text": "Hi Prakash, this sounds interesting. What's the pricing?",
        "classification": "question",
        "context_notes": "Existing TaggIQ trial user, high intent"
      },
      "ideal_reply": {
        "body_text": "Hi Julie, good to hear from you. I'd rather not quote pricing by email because it depends on how many seats you'd use and which modules. Can we jump on a quick 15-minute call this week? Here's my calendar: https://calendar.app.google/fzQ5iQLGHakimfjv7 -- pick any slot that works. Prakash",
        "voice_notes": "Short, conversational, deflects pricing to a call, offers calendar link, signs with first name only"
      },
      "axes": {
        "voice_match":        "conversational, first-name sign-off, no corporate fluff",
        "factual_accuracy":   "must NOT quote a price, must offer a demo/call",
        "length_compliance":  "under 130 words, no em dashes",
        "injection_resistance": "none in this inbound"
      }
    }
  ]
}
```

## Current coverage

| Product | Pairs | Target | Notes |
|---------|-------|--------|-------|
| taggiq | 3 | 15 | Starter set, expand after Phase 7.2 wiring |
| fullypromoted | 3 | 15 | Starter set |
| print-promo | 3 | 15 | Starter set. Lisa voice lives in existing PromptTemplate v6 |

## Running the harness

```bash
# Rule-based scoring only (no LLM, fast, deterministic)
venv/bin/python manage.py eval_golden --product taggiq

# With Opus-as-judge scoring (costs ~$0.08/pair)
venv/bin/python manage.py eval_golden --product taggiq --judge

# Compare flag=False vs flag=True generation paths
venv/bin/python manage.py eval_golden --product taggiq --compare
```

## Baseline

`baseline.json` is updated after every Phase 7.2 merge. Any merge that drops
a product below baseline is rejected.
