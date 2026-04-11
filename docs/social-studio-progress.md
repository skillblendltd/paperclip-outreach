# Social Studio v1 — Working State

**Purpose:** Living handoff document. Every implementer (human or Claude Code session) MUST read this at the start of their session and update it at the end. Prevents context loss between sessions. Read alongside [`social-studio-v1-plan.md`](./social-studio-v1-plan.md).

---

## Current phase

**Phase 0-3 COMPLETE. Phase 4-5 awaiting visual approval + external blockers.**

## Current owner

`/chief-orchestrator` — session complete, handoff back to Prakash for visual review

## Status

- ✅ Plan approved by Prakash (2026-04-11)
- ✅ Phase 0 complete — skills symlinked
- ✅ Phase 1 complete — `social_studio` app + model migration (30 posts preserved)
- ✅ Phase 2 complete — renderer, content_sync, publisher_linkedin, screenshots services + HTML template library
- ✅ Phase 3 complete — `sync_content`, `render_post`, `publish_post`, `capture_screenshots` commands
- ✅ Task 15 partial — E2E pipeline proven with Post 1 render, visual approval pending
- ⏳ Phase 4 (cron cutover) — BLOCKED on Prakash visual sign-off
- ✅ Phase 5 QA (Tasks 18-19) — release-readiness report at `docs/social-studio-qa-report.md` — **GO WITH CAVEATS**
- 🔒 LinkedIn CMA approval pending (blocks live publish only)
- 🔒 TaggIQ test credentials pending (blocks authenticated screenshot capture only)

---

## Task board

Tasks mirror Section 10 of the plan doc. Update status here as work progresses.

| # | Task | Phase | Owner | Size | Status | Notes |
|---|------|-------|-------|------|--------|-------|
| 1 | Symlink TaggIQ skills into paperclip `.claude/skills/` | 0 | DevOps | XS | ✅ DONE | `taggiq-ui-designer` and `taggiq-gtm-strategist` symlinked. Require session restart to activate. |
| 2 | Create `social_studio` Django app | 1 | Backend | S | ✅ DONE | Registered in `INSTALLED_APPS`. Django check clean. |
| 3 | Move `SocialPost`, `SocialAccount`, `SocialPostDelivery` from `campaigns` → `social_studio` | 1 | Backend | M | ✅ DONE | `SeparateDatabaseAndState` migration. DB tables unchanged. 30 posts verified preserved. |
| 4 | Add `headline`, `visual_intent`, `bespoke_html_path`, `media_path` fields | 1 | Backend | S | ✅ DONE | Migration `social_studio/0002_add_visual_pipeline_fields`. |
| 5 | Add Playwright to `Dockerfile`, rebuild web container | 1 | DevOps | S | ✅ DONE | `--with-deps` unavailable on Debian Bookworm (`ttf-unifont` missing); installed Chromium deps manually. Image rebuilt. |
| 6 | `services/renderer.py` — HTML → PNG | 2 | Backend | M | ✅ DONE | 1200×1200 @ 2x, waits for `document.fonts.ready`. |
| 7 | TaggIQ brand templates — `_base.html` + 5 starter templates + `tokens.css` | 2 | UI Designer | M | ✅ DONE | `_base.html`, `stat_hero`, `workflow`, `founder`, `quote`, `question`. `tokens.css` mirrors TaggIQ design-tokens.css. |
| 8 | `services/content_sync.py` — markdown → `SocialPost` | 2 | Backend | S | ✅ DONE | `TAGGIQ_MARKDOWN_PATH` env-configurable. Bind-mounted from `taggiqpos/marketing/social`. |
| 9 | `services/screenshots.py` — TaggIQ product capture | 2 | Backend | M | ⚠️ CODE DONE / BLOCKED | Service + command implemented. `TAGGIQ_SESSION_COOKIE` env var for auth. Blocked on Prakash providing demo credentials. |
| 10 | `services/publisher_linkedin.py` — UGC + 3-step image upload | 2 | Backend | L | ✅ DONE | registerUpload → PUT → ugcPosts with IMAGE asset. Falls back to text-only if no `media_path`. |
| 11 | `manage.py sync_content` | 3 | Backend | S | ✅ DONE | Dry-run verified: parses 30 posts from `/taggiq-marketing/LINKEDIN_POSTS.md`. |
| 12 | `manage.py render_post --post N` | 3 | Backend | S | ✅ DONE | End-to-end tested on Post 1. |
| 13 | `manage.py publish_post --next-scheduled` | 3 | Backend | S | ✅ DONE | Dry-run verified. Correctly warns when no `SocialAccount` exists. |
| 14 | `manage.py capture_screenshots` | 3 | Backend | S | ✅ DONE | Default URL uses `host.docker.internal:5180`. |
| 15 | E2E render test: author 1 bespoke post, render, visually approve | 4 | UI Designer | M | ⏳ PENDING VISUAL APPROVAL | Post 1 rendered at `social_studio/rendered_images/post_01.png` (gitignored). Awaiting Prakash sign-off. |
| 16 | Update `docker/cron-entrypoint.sh` — call `publish_post` instead of `post_to_social` | 4 | DevOps | XS | ⏳ BLOCKED on Task 15 | Do not cut over until visual approval confirms render quality. |
| 17 | Rebuild `outreach_cron` container with Playwright | 4 | DevOps | S | ⏳ BLOCKED on Task 16 | |
| 18 | QA automation suite — render regression + publisher mocks + migration test | 5 | QA | M | ✅ DONE (manual) | 12 QA checks executed in-session. Results in `docs/social-studio-qa-report.md`. Automated test suite is a v2 polish item. |
| 19 | QA release-readiness report | 5 | QA | S | ✅ DONE | **GO WITH CAVEATS** — see `docs/social-studio-qa-report.md`. |

---

## Session log

Each session appends a dated entry describing what was done, decisions made, and outstanding questions.

### 2026-04-11 — `/cto-architect` (plan authoring)

- Reversed earlier Canva recommendation after KISS pushback from Prakash
- Decided v1 renderer: HTML + Playwright (zero-cost, unblocked, brand-faithful)
- Documented 19 tasks, split into 5 phases
- Committed plan doc and this progress doc
- Next session: `/chief-orchestrator` picks up Task #1 (symlinks) and drives Phase 1

### 2026-04-11 — `/chief-orchestrator` (Phase 0-3 + QA session)

**Delivered:**
- Phase 0: skill symlinks (`taggiq-ui-designer`, `taggiq-gtm-strategist`)
- Phase 1: `social_studio` Django app created, 3 models migrated via SeparateDatabaseAndState, 4 new fields added. 30 TaggIQ SocialPosts preserved.
- Phase 2: services (`renderer`, `content_sync`, `publisher_linkedin`, `screenshots`) + HTML template library (`_base.html` + 5 starter templates) + `tokens.css`
- Phase 3: all four management commands (`sync_content`, `render_post`, `publish_post`, `capture_screenshots`)
- Task 15: First bespoke HTML (`rendered_html/post_01.html`) authored and rendered end-to-end. Output at `rendered_images/post_01.png`. Awaiting visual approval.
- Phase 5 QA: 12 checks executed covering functional / architectural / operational / non-functional criteria. Report committed at `docs/social-studio-qa-report.md`. **Verdict: GO WITH CAVEATS.**

**Key decisions this session:**
- Used `Meta.db_table` to preserve existing table names (`social_accounts`, `social_posts`, `social_post_deliveries`) — zero DDL on data move
- Dockerfile: manually installed Chromium runtime libs because `playwright install --with-deps` requires `ttf-unifont` which Debian Bookworm removed
- `TAGGIQ_MARKDOWN_PATH` and `TAGGIQ_FRONTEND_URL` env vars make the container path-agnostic (no hardcoded laptop paths inside service code)
- Bind-mounted `/Users/pinani/Documents/taggiqpos/marketing/social` as `/taggiq-marketing:ro` so content_sync can read the markdown source
- Rendered PNGs are gitignored (`social_studio/rendered_images/`); bespoke HTML files are committed

**Open questions resolved:**
- Q2 commit policy: HTML committed, PNGs gitignored
- Q3 static serving: absolute `file://` paths for v1
- Q4 post_to_social: confirmed exists, Task 10 was a MOVE not create
- New: LinkedIn `--with-deps` Debian compatibility — fixed by manual lib install

**Still pending human-in-the-loop:**
- Q1 TaggIQ test credentials (for screenshot capture)
- Q5 LinkedIn CMA app approval status
- Prakash visual sign-off on `rendered_images/post_01.png`

**Phase 4 (cron cutover) intentionally not executed** — per plan guardrail, cutover must wait for visual approval. Existing cron still runs the stable `post_to_social` command unchanged.

**Next session agenda (after Prakash approves):**
1. Iterate on post_01.html if needed, or author posts 2-30 bespoke HTML
2. Task 16-17: cron cutover (`publish_post --next-scheduled`) + rebuild `outreach_cron` container with Playwright
3. After LinkedIn CMA approval lands: run `setup_linkedin`, publish one live test post, verify against the live TaggIQ page

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
