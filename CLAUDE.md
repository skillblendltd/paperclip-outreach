# Paperclip Outreach

Multi-product B2B outreach system for TaggIQ, Fully Promoted Ireland, and Kritno. Django + SQLite, cron-driven email campaigns with Zoho IMAP/SMTP for reply handling.

## Quick Reference

- **Python**: `venv/bin/python manage.py <command>`
- **Settings**: `outreach/settings.py`
- **All models/views/admin**: `campaigns/` app

## Key Commands

| Command | Purpose |
|---------|---------|
| `send_campaign` | Send outreach emails via SES |
| `process_queue` | Send queued/scheduled emails |
| `check_replies` | Fetch Zoho IMAP, classify inbound, execute auto-actions |
| `review_replies` | Interactive CLI to review flagged replies |
| `seed_reply_templates` | Populate ReplyTemplate table (reference templates) |

## Email Reply Workflow

1. `check_replies` runs via cron every 5 mins — classifies inbound as interested/question/opt_out/bounce/etc.
2. Opt-outs, bounces, not-interested get auto-handled (suppress, disable, cancel queue)
3. Interested, question, other get flagged with `needs_reply=True`
4. Use Claude Code skill `/email-expert` to draft personalized AI replies
5. Review and send via `review_replies` or directly via the skill's send instructions

## Slash Commands

- `/email-expert` — Draft personalized email replies in Prakash's voice. Reads flagged inbound emails, generates warm/conversational replies following real example patterns, includes scheduling links for interested parties.
