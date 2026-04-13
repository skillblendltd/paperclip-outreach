# AI Reply Architecture (Sprint 5 — v5)

The autonomous email reply pipeline. **Org-agnostic by design** — Lisa, TaggIQ, FP Franchise, and any future persona plug in by adding one DB row, no code change required.

## The mental model

```
┌──────────────────────────────────────────────────────────────┐
│  Voice & intent rules  →  PromptTemplate.system_prompt (DB) │ ← persona-specific, UI-editable
│  Persona metadata      →  PromptTemplate.{from_name,        │   (Lisa, Prakash, Emma, etc)
│                            signature_name, max_reply_words} │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  Execution recipe        →  handle_replies._build_execution_preamble()  │ ← ONE source of truth
│  list_pending_replies    →  generic, --product-slug arg                 │   (in code)
│  send_ai_reply           →  generic, takes persona args                 │
│  reply_audit detectors   →  generic, parameterized                       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
                       Claude (Sonnet 4.6)
                       generates body
                              │
                              ▼
                       Pre-send detectors
                       (price/bounce/length)
                              │
                              ▼
                       SMTP via MailboxConfig
                              │
                              ▼
                       EmailLog + AIUsageLog
                              │
                              ▼
                       Mark inbound replied
```

## The contract (org-agnostic)

A persona is fully specified by **one PromptTemplate row**. To add TaggIQ tomorrow, you add a row to `prompt_templates` with:

| Column | Lisa value | TaggIQ value | FP Franchise value |
|---|---|---|---|
| `product_id` | print-promo | taggiq | fullypromoted |
| `feature` | `email_reply` | `email_reply` | `email_reply` |
| `name` | Lisa - FP Kingswood ... | TaggIQ Email Expert ... | FP Franchise Recruiter ... |
| `model` | `claude-sonnet-4-6` | `claude-sonnet-4-6` | `claude-sonnet-4-6` |
| `system_prompt` | Lisa voice rules | TaggIQ voice rules | Prakash voice rules |
| `from_name` | Lisa - Fully Promoted Dublin | Prakash from TaggIQ | Prakash Inani |
| `signature_name` | Lisa | Prakash | Prakash |
| `max_reply_words` | 130 | 180 | 130 |
| `warn_reply_words` | 100 | 130 | 100 |
| `is_active` | True | True | True |

**No code changes.** No new commands. No new detectors. Just one row per persona.

## Components

### `campaigns/services/reply_audit.py`

Pure-function detectors used by both `send_ai_reply` (pre-send blocking) and `handle_replies` (post-run audit).

```python
from campaigns.services.reply_audit import (
    detect_price_violation,    # → match string or None
    detect_bounce_reply,       # → bool
    detect_length_violation,   # → (word_count, severity)
    run_all_checks,            # → list of (severity, code, message)
)
```

All functions take `signature_name` as a parameter so the persona's signature block (address, phone, name) is stripped before scanning. Length thresholds are also parameters — no Lisa-shaped defaults.

### `manage.py list_pending_replies --product-slug X`

Replaces the old inline Django shell from Step 1 of every prompt. Generic — same command for every persona, just different `--product-slug`.

```bash
python manage.py list_pending_replies --product-slug print-promo
python manage.py list_pending_replies --product-slug taggiq --limit 20
```

Skips inbounds whose `ai_attempt_count >= 5` so retry-exhausted inbounds stop showing.

### `manage.py send_ai_reply`

The single execution endpoint. Every persona prompt calls this exact command.

```bash
python manage.py send_ai_reply \
  --inbound-id <UUID> \
  --subject "Re: ..." \
  --body-html "<p>Hi ...</p>" \
  --from-name "Lisa - Fully Promoted Dublin" \
  --signature-name "Lisa" \
  --max-words 130 \
  --warn-words 100
```

What it does internally:
1. Fetch inbound + prospect + campaign + product
2. Check retry budget — exit 5 if exhausted
3. Run all 3 detectors PRE-SEND — exit 2/3/4 on any fail
4. Resolve SMTP via `MailboxConfig` with sibling-campaign fallback
5. Send via `EmailService.send_reply` with proper threading headers
6. Create `EmailLog` audit row
7. Mark inbound `replied=True`, increment `ai_attempt_count`
8. Log to `AIUsageLog` for per-persona cost tracking

#### Exit codes (stable contract — prompts depend on these)

| Code | Meaning | What Claude should do |
|---|---|---|
| `0` | Success | Move to next inbound |
| `1` | Generic error (inbound not found, SMTP failure, etc) | Read error, move on |
| `2` | PRICE-QUOTE blocked | Rewrite body without any currency-anchored number, retry |
| `3` | BOUNCE-REPLY blocked | Skip this inbound entirely (already marked needs_reply=False) |
| `4` | LENGTH-FAIL blocked | Rewrite shorter, retry |
| `5` | Retry budget exhausted | Give up, move on (already marked for manual review) |

Each non-zero exit prints a structured error message to stderr explaining what failed and what Claude should do next.

### `handle_replies._build_execution_preamble(product, prompt_template)`

The persona-parameterized recipe that gets prepended to every DB prompt at runtime. Lives in code so it stays consistent across personas. Substitutes:

- `{{product_slug}}` → e.g. `print-promo`
- `{{from_name}}` → e.g. `Lisa - Fully Promoted Dublin`
- `{{signature_name}}` → e.g. `Lisa`
- `{{max_words}}` / `{{warn_words}}` → from PromptTemplate fields

Output is the Step 1-4 execution recipe with the right slug + persona baked in. Each cron invocation assembles:

```
[execution preamble]   ← from code, ~3000 chars
+
[voice rules]          ← from PromptTemplate.system_prompt, ~5-8K chars
+
[per-call kicker]      ← "there are N inbounds, handle them all"
```

Then sends as the `-p` arg to Claude CLI.

### `MailboxConfig` resolution with fallback

```python
def _resolve_smtp_config(campaign, product):
    # 1. Direct lookup
    mb = MailboxConfig.objects.filter(campaign=campaign, is_active=True).first()
    if mb: return mb.get_smtp_config()
    # 2. Sibling campaign in same product
    mb = MailboxConfig.objects.filter(campaign__product_ref=product, is_active=True).first()
    if mb: return mb.get_smtp_config()
    return None
```

Why: Dublin Construction has no MailboxConfig of its own but Kingswood does, and they share `office@fullypromoted.ie`. Same pattern protects against any future data gaps.

## Multi-tenancy guarantees

Every layer enforces the org/product boundary:

| Layer | How |
|---|---|
| `PromptTemplate` | FK → Product → Organization. Lisa's prompt cannot leak into TaggIQ. |
| `list_pending_replies` | Filters `campaign__product_ref__slug=X`. Cross-product invisible. |
| `send_ai_reply` | Looks up product via inbound → campaign → product_ref. SMTP routed via that product's MailboxConfig only. |
| `AIUsageLog` | Records `organization`, `product`, `campaign` on every row. Per-tenant cost queries are trivial. |
| `handle_replies --product / --exclude-product` | Cron-level scoping, used to partition between laptop and EC2. |

## Failure modes & guarantees

| Failure | What happens |
|---|---|
| Claude generates a price quote | Pre-send detector (exit 2) refuses to send. Body never reaches customer. |
| Claude tries to reply to a bounce | Pre-send detector (exit 3) refuses. Inbound marked `needs_reply=False`. |
| Claude generates a wall-of-text reply | Pre-send detector (exit 4) refuses. Forces rewrite. |
| Claude can't fix a violation in 5 attempts | `ai_attempt_count` hits the ceiling. send_ai_reply (exit 5) marks inbound for manual review. |
| Claude CLI crashes / times out | `handle_replies` catches subprocess timeout. Logs error. Inbound stays flagged for next cron tick. |
| MailboxConfig is missing for a campaign | Falls back to sibling MailboxConfig in the same product. Only fails if NO MailboxConfig exists for the entire product. |
| SMTP send fails | `send_ai_reply` exit 1, AIUsageLog row written with `success=False`, inbound `ai_attempt_count` incremented. |

## How to add a new persona (TaggIQ example)

1. **Write the voice rules.** Open the Paperclip UI → Prompt Templates → New. Set `product=TaggIQ`, `feature=email_reply`, write the system_prompt as voice/intent/rules only (no Django shell, no execution recipe). Set `from_name="Prakash from TaggIQ"`, `signature_name="Prakash"`, `max_reply_words=180`, `warn_reply_words=130`.

2. **Verify mailboxes exist.** Each TaggIQ campaign should already have a MailboxConfig. If any are missing, the sibling fallback kicks in.

3. **Run a smoke test:**
   ```bash
   python manage.py list_pending_replies --product-slug taggiq
   python manage.py handle_replies --product taggiq --dry-run
   ```

4. **Enable in cron.** Update the cron host's `CRON_REPLY_ARGS` env var to include or exclude `taggiq` per the partition strategy.

5. **Watch the audit.** First real inbound flows through — verify the AIUsageLog row appears, EmailLog audit row created, and the post-run audit either logs `audit clean` or surfaces a violation. Iterate the prompt voice rules in the UI based on what you see.

**No code change.** No deploy. No new commands. The whole onboarding is one DB row + one env var update.

## Cost observability

Every `send_ai_reply` invocation writes an `AIUsageLog` row. Per-persona cost is queryable:

```sql
SELECT product.slug, COUNT(*), SUM(cost_usd)
FROM ai_usage_log
JOIN products product ON ai_usage_log.product_id = product.id
WHERE feature = 'email_reply' AND created_at > NOW() - INTERVAL '30 days'
GROUP BY product.slug;
```

Or in the Django shell:

```python
from campaigns.models import AIUsageLog
from django.db.models import Sum, Count
AIUsageLog.objects.filter(feature='email_reply').values('product__slug').annotate(
    n=Count('id'), cost=Sum('cost_usd'),
)
```

## What's deliberately NOT in the design

- **No prompt caching.** Anthropic supports it but Lisa's daily volume is ~10 replies — caching saves <$3/month. Add when total Claude spend hits $50+/month.
- **No eval fixture suite.** Build organically from real failure cases. Don't write 10 fictional fixtures upfront.
- **No structured JSON logging.** Free-text logger.error/warning is enough until you need analytics over thousands of runs.
- **No alerting on consecutive Claude failures.** Add when you experience the first silent outage.

These are deferred deliberately. Don't pre-build them.

## Sprint 5 v5 verification checklist

- [x] Migrations 0015 applied on both laptop + EC2 DBs
- [x] `reply_audit.py` service module created with parameterized detectors
- [x] `list_pending_replies` command shipped
- [x] `send_ai_reply` command shipped with all 5 exit codes verified
- [x] `handle_replies._build_execution_preamble` parameterizes by persona
- [x] Lisa v5 prompt active in both DBs (8424 chars voice-only, down from 12601)
- [x] AIUsageLog rows written by send_ai_reply
- [x] MailboxConfig sibling-fallback verified on Construction
- [x] Detector signature stripping verified for both Lisa and Prakash personas
- [x] Code committed and pushed: `ec5601a`
- [ ] First real autonomous reply via v5 pipeline (waiting for next inbound)
