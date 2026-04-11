# Social Studio v1 - Architectural Plan

**Date:** 2026-04-11
**Status:** Approved, ready for implementation
**Owner:** Prakash Inani (product) · `/cto-architect` (architecture) · `/chief-orchestrator` (delivery)
**Pilot tenant:** TaggIQ
**Target outcome:** Autonomously publish the 30-post TaggIQ LinkedIn content plan with professional branded visuals, zero cost, zero manual steps at publish time.

---

## 1. Platform framing

Paperclip is a sales automation platform with three independently shippable modules:

```
paperclip-outreach/
├── campaigns/         Module 1: Email outreach   (existing - universal sender, IMAP reply engine)
├── calling/           Module 2: Voice calling     (currently inside campaigns, extract later)
└── social_studio/     Module 3: Social posting    (NEW - this plan)
```

Each module is tenant-scoped via the existing `Organization → Product → Campaign` hierarchy. Each module can be sold standalone or bundled. Every architectural decision must preserve this separation.

**Monetization posture (documented, not built):** modules can be sold individually or as a bundle. When we sell Social Studio to a customer who isn't TaggIQ or Fully Promoted, the customer becomes a new `Product` under their `Organization`. No code changes required to onboard.

---

## 2. Non-goals for v1

Explicitly deferred. Each has a clean hook in v1 architecture:

- Canva Connect API integration (v2 feature - customers bring their own Canva brand kit)
- AI image generation (Gemini / DALL-E / gpt-image)
- Multi-channel publishing (Facebook, Instagram, Twitter, Google Business) - stubs only
- Engagement metrics loop
- Admin UI / dashboard
- Billing / plans / customer onboarding flows
- Brand, Template, Publication, VisualAsset models - v1 uses flat fields on `SocialPost`
- White-label / agency tier
- Webhook receivers for Canva or LinkedIn
- Fully Promoted Ireland tenant setup (architecture supports it; setup happens when FP needs it)

**KISS directive:** zero abstractions until the third time we need one. No Brand model when a tenant folder + a design-tokens CSS file works. No Template model when an HTML file works. No Publication model when one post goes to one channel.

---

## 3. v1 capability

**Input:** a markdown file of 30 posts authored by `/gtm-strategist` (lives in the taggiqpos repo at `marketing/social/LINKEDIN_POSTS.md`)

**Output:** autonomous daily publication to TaggIQ's LinkedIn Company Page with branded 1200×1200 PNGs

**Constraints:**
- $0 total tool cost
- No third-party approvals beyond LinkedIn Community Management API (already in flight)
- Bespoke-per-post visuals, not rigid templates
- Professional quality matching what Prakash produces manually (founder-led SaaS brand aesthetic)

---

## 4. Module layout

```
social_studio/
├── apps.py
├── models.py                    # SocialPost, SocialAccount (migrated from campaigns/)
├── services/
│   ├── __init__.py
│   ├── content_sync.py          # LINKEDIN_POSTS.md → SocialPost rows
│   ├── renderer.py              # Playwright: HTML file → 1200x1200 PNG
│   ├── screenshots.py           # Playwright: localhost:5180 → PNG (TaggIQ product capture)
│   └── publisher_linkedin.py    # LinkedIn UGC API + 3-step image asset upload
├── templates/social/taggiq/     # HTML starting-point templates (designer can override per post)
│   ├── _base.html               # shared brand container: logo, footer, tokens
│   ├── stat_hero.html
│   ├── workflow.html
│   ├── founder.html
│   ├── quote.html
│   └── question.html
├── static/social/taggiq/
│   └── tokens.css               # TaggIQ design tokens (mirrors taggiqpos design-tokens.css)
├── rendered_html/               # bespoke HTML per post written by /taggiq-ui-designer
├── rendered_images/             # output PNGs (what LinkedIn uploads)
├── management/commands/
│   ├── sync_content.py          # parse markdown → SocialPost rows
│   ├── render_post.py           # SocialPost ID → Playwright → PNG
│   ├── publish_post.py          # SocialPost ID → LinkedIn upload
│   └── setup_linkedin.py        # (moved from campaigns/)
├── migrations/
└── admin.py                     # minimal Django admin for SocialPost/SocialAccount
```

**Multi-tenant extension path (documented, not built for FP yet):**
```
social_studio/templates/social/fullypromoted/
social_studio/static/social/fullypromoted/tokens.css
```
Adding FP = copy one folder, edit tokens. Zero Python changes.

---

## 5. Data model changes

### Models to migrate (from `campaigns/models.py` → `social_studio/models.py`)

- `SocialAccount` - OAuth credentials per product per platform
- `SocialPost` - content + scheduling
- `SocialPostDelivery` - per-channel publish record

Migration is data-preserving: the 30 seeded TaggIQ posts must survive intact.

### Fields to add on `SocialPost`

```python
headline = models.CharField(max_length=280, blank=True)
# Short hook for the visual (separate from full post body).
# Author provides explicitly, no auto-extraction.

visual_intent = models.CharField(
    max_length=32,
    choices=[
        ('typography_only', 'Text / typography only'),
        ('product_screenshot', 'Product screenshot composite'),
        ('bespoke_html', 'Bespoke HTML authored by designer'),
    ],
    default='bespoke_html',
)
# Author's declared intent. Renderer uses this to pick the code path.

bespoke_html_path = models.CharField(max_length=500, blank=True)
# Relative path to the bespoke HTML file for this post.
# e.g. 'rendered_html/post_01.html'

media_path = models.CharField(max_length=500, blank=True)
# Relative path to the rendered PNG.
# e.g. 'rendered_images/post_01.png'
# Populated by render_post. Consumed by publish_post.
```

No other schema changes in v1.

---

## 6. The two flows

### Design time (manual, in-session, bespoke per post)

```
1. Author: /gtm-strategist writes or updates LINKEDIN_POSTS.md (30 posts)

2. Author: python manage.py sync_content --brand taggiq
   → parses markdown → upserts SocialPost rows

3. Author: per post, invoke /taggiq-ui-designer
   → reads post content + TaggIQ product context
   → writes rendered_html/post_N.html (freely composed, using templates/social/taggiq/
      as starting points or from scratch, embedding screenshots from static/taggiq-ui/)
   → updates SocialPost.bespoke_html_path

4. Author: python manage.py render_post --post N
   → Playwright loads the HTML at 1200×1200, wait for fonts, screenshot
   → saves to rendered_images/post_N.png
   → updates SocialPost.media_path

5. Author eyeballs the PNG, iterates if needed (edit HTML, re-render)
```

### Runtime (autonomous, cron)

```
0 9 * * 1-5 → python manage.py publish_post --next-scheduled
    → picks SocialPost where scheduled_date == today AND media_path is set
    → for each attached SocialAccount (TaggIQ LinkedIn page):
        → uploads PNG via LinkedIn 3-step image asset flow:
            1. POST /v2/assets?action=registerUpload
            2. PUT <uploadUrl> with binary bytes
            3. POST /v2/ugcPosts with shareMediaCategory=IMAGE and asset URN
        → creates SocialPostDelivery record
    → marks post as published
```

Cron has zero AI, zero design, zero creative dependencies. It's dumb distribution. All creativity happens upstream in the design-time flow.

---

## 7. The renderer: HTML + Playwright

**Why HTML + Playwright over alternatives:**

| Option | Cost | Blocked by | Brand fidelity | Autonomy |
|--------|------|-----------|----------------|----------|
| **HTML + Playwright** | **$0** | **Nothing** | **Uses real TaggIQ design tokens** | **Fully autonomous** |
| Canva Connect API | Enterprise license | Canva approval + subscription | Template-locked | In-session only (MCP) or autonomous (paid Connect API) |
| Gemini / DALL-E | Free tier (limited) | Nothing | Inconsistent, AI-look | Autonomous |
| Pillow text overlay | $0 | Nothing | Weak - no real UI possible | Autonomous |

HTML + Playwright is the only option that is simultaneously free, unblocked, brand-faithful, and autonomous.

**Implementation sketch:**

```python
# social_studio/services/renderer.py
from playwright.sync_api import sync_playwright
from pathlib import Path

CANVAS_SIZE = (1200, 1200)

def render_html_to_png(html_path: Path, out_path: Path) -> Path:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={'width': CANVAS_SIZE[0], 'height': CANVAS_SIZE[1]},
            device_scale_factor=2,  # retina
        )
        page = context.new_page()
        page.goto(f'file://{html_path.resolve()}')
        page.wait_for_load_state('networkidle')
        page.wait_for_function('document.fonts.ready')
        page.screenshot(path=str(out_path), omit_background=False, full_page=False, clip={
            'x': 0, 'y': 0, 'width': CANVAS_SIZE[0], 'height': CANVAS_SIZE[1],
        })
        browser.close()
    return out_path
```

**Playwright install in Docker:** `pip install playwright` + `playwright install --with-deps chromium` in the Dockerfile. Adds ~400 MB to the image. Accepted.

---

## 8. The capture service

`services/screenshots.py` uses Playwright to capture real TaggIQ product screens from `http://localhost:5180/<route>` (the live TaggIQ frontend already running in Docker). Captured PNGs become static assets that bespoke HTML posts can embed.

```python
TAGGIQ_ROUTES_TO_CAPTURE = [
    ('dashboard', '/'),
    ('quote-builder', '/quotes/new'),
    ('supplier-search', '/products'),
    ('artwork-approval', '/artworks'),
    ('invoicing', '/invoices'),
    ('live-presentation', '/quotes/presentation/demo'),
]
```

Output: `static/taggiq-ui/<name>.png` (1440×900 viewport, cropped to content). Run on demand (`python manage.py capture_screenshots`) when the TaggIQ product UI changes, not per-post.

**Dependency:** requires a logged-in test account or public demo data. Implementer must coordinate with TaggIQ product team for credentials or seed a demo org.

---

## 9. Publisher (LinkedIn)

Moves from `campaigns/management/commands/post_to_social.py` into `social_studio/services/publisher_linkedin.py`, adds the missing IMAGE upload step.

**LinkedIn 3-step image upload (required for posts with attached images):**

```
1. POST https://api.linkedin.com/v2/assets?action=registerUpload
   Body: { "registerUploadRequest": {
       "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
       "owner": "urn:li:organization:<page_id>",
       "serviceRelationships": [{ "relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent" }]
   }}
   → returns { "value": { "uploadMechanism": {...uploadUrl...}, "asset": "urn:li:digitalmediaAsset:..." } }

2. PUT <uploadUrl>
   Body: <PNG binary bytes>
   Headers: Authorization: Bearer <access_token>

3. POST https://api.linkedin.com/v2/ugcPosts
   Body: {
       "author": "urn:li:organization:<page_id>",
       "lifecycleState": "PUBLISHED",
       "specificContent": {
           "com.linkedin.ugc.ShareContent": {
               "shareCommentary": { "text": "<post body + hashtags>" },
               "shareMediaCategory": "IMAGE",
               "media": [{
                   "status": "READY",
                   "media": "urn:li:digitalmediaAsset:..."
               }]
           }
       },
       "visibility": { "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC" }
   }
```

**Dependency:** LinkedIn Community Management API approval. Application already submitted for a separate dedicated app (tracked separately). Runtime testing blocked until approval. Render pipeline is unblocked.

---

## 10. Implementation tasks

All tasks tracked in `docs/social-studio-progress.md`. Implementer must update the progress doc after each task to preserve cross-session context.

| # | Task | Phase | Owner | Size | Depends on |
|---|------|-------|-------|------|-----------|
| 1 | Symlink TaggIQ `ui-designer` + `gtm-strategist` skills into `paperclip-outreach/.claude/skills/` | 0 | DevOps | XS | - |
| 2 | Create `social_studio` Django app, register in settings, empty migrations | 1 | Backend | S | - |
| 3 | Data-preserving migration: move `SocialPost`, `SocialAccount`, `SocialPostDelivery` from `campaigns` → `social_studio` | 1 | Backend | M | 2 |
| 4 | Add `headline`, `visual_intent`, `bespoke_html_path`, `media_path` fields to `SocialPost` | 1 | Backend | S | 3 |
| 5 | Add Playwright + Chromium to Dockerfile, rebuild web container | 1 | DevOps | S | - |
| 6 | `services/renderer.py` - HTML file → PNG via Playwright | 2 | Backend | M | 5 |
| 7 | Copy TaggIQ `design-tokens.css` → `static/social/taggiq/tokens.css` + `_base.html` brand container + 5 starter HTML templates | 2 | UI Designer | M | - |
| 8 | `services/content_sync.py` - parse `LINKEDIN_POSTS.md` → `SocialPost` rows (upsert by `post_number`) | 2 | Backend | S | 4 |
| 9 | `services/screenshots.py` - capture 6 TaggIQ routes from localhost:5180 → `static/taggiq-ui/` | 2 | Backend | M | 5 |
| 10 | `services/publisher_linkedin.py` - LinkedIn UGC + 3-step image asset upload, moved from `campaigns/` | 2 | Backend | L | 3 |
| 11 | `manage.py sync_content` command | 3 | Backend | S | 8 |
| 12 | `manage.py render_post --post N` command | 3 | Backend | S | 6, 7 |
| 13 | `manage.py publish_post --next-scheduled` command | 3 | Backend | S | 10 |
| 14 | `manage.py capture_screenshots` command | 3 | Backend | S | 9 |
| 15 | End-to-end render test: author 1 post via `/taggiq-ui-designer`, render, visually approve | 4 | UI Designer | M | 11, 12 |
| 16 | Update `docker/cron-entrypoint.sh` - replace `post_to_social` with `publish_post --next-scheduled` | 4 | DevOps | XS | 13 |
| 17 | Rebuild `outreach_cron` container with Playwright | 4 | DevOps | S | 16 |
| 18 | QA automation suite - render regression (golden-file PNGs), publisher unit tests with mocked LinkedIn, data migration test | 5 | QA | M | 15 |
| 19 | QA release-readiness report for TaggIQ validation | 5 | QA | S | 18 |

**Not in this list (blocked by LinkedIn CMA approval, separate track):**
- Live LinkedIn publish test (runs after CMA approval lands)

---

## 11. QA release-readiness criteria

QA must verify all of the following before declaring TaggIQ validation ready:

### Functional
- [ ] `sync_content` parses the TaggIQ markdown and creates/updates 30 `SocialPost` rows
- [ ] Data migration preserved all existing TaggIQ social post content (count match, headline match on random sample)
- [ ] `render_post --post N` produces a 1200×1200 PNG for at least 5 bespoke-HTML posts authored via `/taggiq-ui-designer`
- [ ] Rendered PNGs pass visual inspection (font rendering, TaggIQ violet, logo placement, no overflow)
- [ ] `capture_screenshots` successfully captures at least 3 TaggIQ routes
- [ ] `publish_post` successfully uploads an image via LinkedIn 3-step flow **against a mocked LinkedIn API**
- [ ] Cron entrypoint runs `publish_post --next-scheduled` without crashing

### Architectural
- [ ] `social_studio` has zero imports from inside `campaigns/` (except `Organization`, `Product` FK resolution)
- [ ] `campaigns` has zero imports from `social_studio`
- [ ] Module boundary enforced: `social_studio` can be deleted without breaking `campaigns`
- [ ] Django app registered cleanly in settings

### Operational
- [ ] Docker web + cron containers build with Playwright installed
- [ ] Chromium renders one HTML file successfully inside the web container
- [ ] `rendered_html/`, `rendered_images/`, `static/taggiq-ui/` gitignored or committed per team policy

### Non-functional
- [ ] No secrets in committed files
- [ ] No hardcoded laptop paths in the rendering pipeline
- [ ] `docs/social-studio-progress.md` is up to date with final state

### Release readiness verdict

QA produces a final report: `GO` / `NO-GO` / `GO-WITH-CAVEATS` for TaggIQ pilot launch, pending only LinkedIn CMA approval for the publish step.

---

## 12. Progress tracking

Implementers MUST keep `docs/social-studio-progress.md` up to date. The orchestrator reads this file at the start of every session to recover context. After each task is completed, append the result and any learnings to the progress doc. If a session ends mid-task, the progress doc must capture enough state for the next session to resume without asking.

---

## 13. Open questions (answer before implementation starts)

1. **LINKEDIN_POSTS.md location** - is the canonical source `/Users/pinani/Documents/taggiqpos/marketing/social/LINKEDIN_POSTS.md` or should it be mirrored into `paperclip-outreach/social_studio/content/taggiq/LINKEDIN_POSTS.md`? Recommended: keep source of truth in `taggiqpos`, `sync_content` reads it via configured absolute path stored in settings/env.
2. **TaggIQ frontend credentials** - `screenshots.py` needs a way to auth into the running TaggIQ app. Does Prakash have a demo account, or do we need to seed one?
3. **Rendered HTML + PNG commit policy** - commit the bespoke HTML and rendered PNGs to git for reproducibility, or gitignore and rebuild on demand? Recommended: commit HTML (small, auditable), gitignore PNGs (large, regeneratable).
4. **Static asset delivery for Playwright rendering** - when Playwright opens `file://rendered_html/post_01.html`, the HTML must be able to `<link>` to `static/social/taggiq/tokens.css` and `<img>` from `static/taggiq-ui/*.png`. Implementer must pick a path resolution strategy (absolute paths, symlinks, or a local HTTP server). Recommended: use a local `python -m http.server` on an unused port during render, navigate to `http://localhost:<port>/rendered_html/post_01.html`.

---

## 14. Rollback strategy

If any phase ships broken state:
- Phase 1 (app creation + model migration): roll back the migration with `./manage.py migrate social_studio zero` and delete the app. `campaigns` unchanged.
- Phase 2 (services): services are pure Python modules. Delete the file. Nothing else references them until Phase 3 commands exist.
- Phase 3 (commands): delete the command file. Cron still runs the old `post_to_social` command until Phase 4.
- Phase 4 (cron cutover): revert `cron-entrypoint.sh` to call `post_to_social`, rebuild cron container.

Each phase is independently reversible.

---

## 15. References

- Existing platform docs: `docs/architecture-v2-plan.md`, `docs/sprint-plan.md`, `CLAUDE.md`
- TaggIQ design tokens: `/Users/pinani/Documents/taggiqpos/frontend/src/styles/design-tokens.css`
- TaggIQ UI Designer skill: `/Users/pinani/Documents/taggiqpos/.claude/skills/ui-designer/SKILL.md`
- TaggIQ GTM Strategist skill: `/Users/pinani/Documents/taggiqpos/.claude/skills/gtm-strategist/SKILL.md`
- TaggIQ logo: `/Users/pinani/Documents/paperclip-outreach/campaigns/assets/brand/taggiq-logo.png`
- LinkedIn API docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api
