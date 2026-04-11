# Social Studio v1 — Working State

**Purpose:** Living handoff document. Every implementer (human or Claude Code session) MUST read this at the start of their session and update it at the end. Prevents context loss between sessions. Read alongside [`social-studio-v1-plan.md`](./social-studio-v1-plan.md).

---

## Current phase

**Phase 0 — Pre-implementation**

## Current owner

`/chief-orchestrator` — awaiting first session pickup

## Status

- ✅ Architectural plan approved by Prakash (2026-04-11)
- ✅ Plan committed at `docs/social-studio-v1-plan.md`
- ⏳ Implementation not yet started
- 🔒 LinkedIn Community Management API approval pending (blocks Task #15 live test, does NOT block Tasks 1-14)

---

## Task board

Tasks mirror Section 10 of the plan doc. Update status here as work progresses.

| # | Task | Phase | Owner | Size | Status | Notes |
|---|------|-------|-------|------|--------|-------|
| 1 | Symlink TaggIQ skills into paperclip `.claude/skills/` | 0 | DevOps | XS | Pending | Single `ln -s` for `ui-designer` + `gtm-strategist` from `/Users/pinani/Documents/taggiqpos/.claude/skills/` |
| 2 | Create `social_studio` Django app | 1 | Backend | S | Pending | `python manage.py startapp social_studio`, add to `INSTALLED_APPS` |
| 3 | Move `SocialPost`, `SocialAccount`, `SocialPostDelivery` from `campaigns` → `social_studio` | 1 | Backend | M | Pending | Data-preserving. Existing 30 TaggIQ posts must survive. |
| 4 | Add `headline`, `visual_intent`, `bespoke_html_path`, `media_path` fields | 1 | Backend | S | Pending | See plan §5 for exact field definitions |
| 5 | Add Playwright to `Dockerfile`, rebuild web container | 1 | DevOps | S | Pending | `pip install playwright` + `playwright install --with-deps chromium` |
| 6 | `services/renderer.py` — HTML → PNG | 2 | Backend | M | Pending | Reference implementation in plan §7 |
| 7 | TaggIQ brand templates — `_base.html` + 5 starter templates + `tokens.css` | 2 | UI Designer | M | Pending | Copy design tokens from taggiqpos repo |
| 8 | `services/content_sync.py` — markdown → `SocialPost` | 2 | Backend | S | Pending | Source: `/Users/pinani/Documents/taggiqpos/marketing/social/LINKEDIN_POSTS.md` |
| 9 | `services/screenshots.py` — TaggIQ product capture | 2 | Backend | M | Pending | Needs test account credentials — see Open Q#2 |
| 10 | `services/publisher_linkedin.py` — UGC + 3-step image upload | 2 | Backend | L | Pending | Moved from `campaigns/`, adds IMAGE flow |
| 11 | `manage.py sync_content` | 3 | Backend | S | Pending | |
| 12 | `manage.py render_post --post N` | 3 | Backend | S | Pending | |
| 13 | `manage.py publish_post --next-scheduled` | 3 | Backend | S | Pending | |
| 14 | `manage.py capture_screenshots` | 3 | Backend | S | Pending | |
| 15 | E2E render test: author 1 bespoke post, render, visually approve | 4 | UI Designer | M | Pending | Blocks on #11-#12 |
| 16 | Update `docker/cron-entrypoint.sh` — call `publish_post` instead of `post_to_social` | 4 | DevOps | XS | Pending | |
| 17 | Rebuild `outreach_cron` container with Playwright | 4 | DevOps | S | Pending | |
| 18 | QA automation suite — render regression + publisher mocks + migration test | 5 | QA | M | Pending | See plan §11 for coverage |
| 19 | QA release-readiness report | 5 | QA | S | Pending | Final GO/NO-GO for TaggIQ pilot |

---

## Session log

Each session appends a dated entry describing what was done, decisions made, and outstanding questions.

### 2026-04-11 — `/cto-architect` (plan authoring)

- Reversed earlier Canva recommendation after KISS pushback from Prakash
- Decided v1 renderer: HTML + Playwright (zero-cost, unblocked, brand-faithful)
- Documented 19 tasks, split into 5 phases
- Committed plan doc and this progress doc
- Next session: `/chief-orchestrator` picks up Task #1 (symlinks) and drives Phase 1

### 2026-04-11 — `/chief-orchestrator` (claimed, Phase 0-3 execution)

**Open questions resolved:**
- Q2 (commit policy): commit HTML files, gitignore rendered PNG output
- Q3 (static serving): `file://` with absolute paths for v1, revisit if Playwright complains
- Q4 (post_to_social): confirmed exists at `campaigns/management/commands/post_to_social.py` — Task #10 is a MOVE

**Open questions still blocking:**
- Q1 (TaggIQ test credentials): needed for Task #9 (capture_screenshots). Flagging to Prakash.
- Q5 (LinkedIn CMA app approval status): blocks live publishing (Task #17+ only). Flagging to Prakash.

**DB state baseline before migration:**
- SocialPost: 30 rows (all TaggIQ, must preserve)
- SocialAccount: 0 rows (no OAuth yet)
- SocialPostDelivery: 0 rows
- SocialPost current fields: `product, post_number, content, hashtags, link_url, media_url, media_description, pillar, scheduled_date`

**Migration strategy for Task #3:**
Use `class Meta: db_table = 'campaigns_socialpost'` (and equivalents) on the new `social_studio` models. DB table names stay put; only Django ORM ownership moves. Zero data risk. Django migration uses `SeparateDatabaseAndState` pattern.

**Execution plan for this session:** Drive Phase 0 → Phase 3 inclusive (Tasks 1-14 excluding #9 which is blocked on credentials). Stop at Task 15 (E2E render test) for Prakash visual approval before Phase 4 cutover.

---

## Decisions log

Important decisions and their context. Append-only — if a decision is reversed, add a new entry referencing the old one.

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-11 | `social_studio` becomes a separate Django app, not a submodule of `campaigns` | Platform thinking: enables selling email/voice/social modules independently |
| 2026-04-11 | HTML + Playwright for v1 renderer, zero Canva | Free, unblocked, brand-faithful, autonomous-capable |
| 2026-04-11 | Bespoke HTML per post (author runs `/taggiq-ui-designer` in session) instead of rigid templates | Author requested non-template flexibility; templates become starting points, not constraints |
| 2026-04-11 | Canva Connect API deferred to v2 as a customer feature | "Customers bring their own Canva brand kit" — not needed for TaggIQ pilot |
| 2026-04-11 | AI image generation (Gemini etc.) not used in v1 | Inconsistent brand, free tier limited, not needed when HTML can achieve target quality |
| 2026-04-11 | LinkedIn CMA approval gates live testing only, not the build | Render pipeline works standalone without real LinkedIn calls |
| 2026-04-11 | Keep source-of-truth `LINKEDIN_POSTS.md` in `taggiqpos` repo; `sync_content` reads it via configured path | Content lives next to the product it promotes |

---

## Open questions

Implementers must resolve these before or during the first relevant task.

1. **TaggIQ frontend test credentials** — Task #9 (`capture_screenshots`) needs a logged-in session to reach product pages. Does Prakash have a demo account, or do we create one? Blocks Task #9 and #14.
2. **Rendered PNG commit policy** — commit or gitignore? Plan recommends commit HTML, gitignore PNGs. Confirm during Task #7.
3. **Static asset serving for Playwright** — `file://` vs. local HTTP server? Plan recommends local HTTP server on unused port. Confirm during Task #6.
4. **`post_to_social` command** — does it currently exist in `campaigns/management/commands/`? If yes, Task #10 moves it; if no, Task #10 creates from scratch. Orchestrator must check and report.
5. **LinkedIn CMA app state** — is a separate dedicated LinkedIn app for CMA already created and awaiting approval? Orchestrator should confirm by reading recent session history or asking Prakash.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Data loss during `SocialPost` migration | Low | High | Golden-file backup of `SocialPost` table before Task #3; migration test in Task #18 |
| Playwright Docker image size / build time | Medium | Low | Accepted — ~400 MB add. Build once, cache layers |
| Playwright fails inside `outreach_cron` container (Chromium deps) | Medium | Medium | `playwright install --with-deps` handles most; test in Task #17 |
| LinkedIn API changes between build and CMA approval | Low | Medium | Publisher is thin wrapper; change blast radius is one file |
| Bespoke HTML authoring proves too slow for 30 posts | Medium | Medium | Fallback: use one of the 5 starter templates with minimal customization. Document in session log if this happens. |

---

## Handoff protocol (for orchestrator and agents)

When ending a session:
1. Update task statuses in the table above
2. Append a session log entry dated today
3. Add any new decisions to the Decisions log
4. Add any new open questions or risks discovered during the session
5. Commit the updated progress doc with message `progress: social-studio-v1 <phase> — <short summary>`

When starting a session:
1. Read this file first, then the plan doc
2. Read the most recent session log entry
3. Check open questions — resolve any that block your task
4. Claim the next `Pending` task in order (respecting `Depends on` column in the plan)
5. Mark it `In Progress` here before starting

---

## Exit criteria for v1

- All 19 tasks complete
- Phase 5 QA report marked `GO` or `GO-WITH-CAVEATS`
- At least 1 bespoke post rendered end-to-end and visually approved by Prakash
- Docker cron container runs `publish_post` without error
- LinkedIn CMA approval landed AND one live publish succeeded against the TaggIQ Company Page
- This progress doc captures the final state
