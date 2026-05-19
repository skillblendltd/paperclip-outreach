# LinkedIn DM Follow-up - Architecture & Plan

**Author:** CTO Architect
**Date:** 2026-05-18
**Status:** DESIGN
**Depends on:** `docs/linkedin-automation-plan.md` (connection automation)

---

## 1. Scope

After a LinkedIn connection request is accepted, send a personalized first DM. Reply intelligently to inbound DMs. Treat LinkedIn as a first-class outbound channel alongside email and voice in the Paperklip pipeline.

This doc designs the **data model, integration points, and provider abstraction** so that DM automation drops in cleanly whenever API access becomes available. The actual send-side adapter (browser / Unipile / official API / Sales Navigator) is intentionally a swappable plug, not a fixed choice.

**In scope:**
- Schema for person enrichment notes (the "note person" requirement)
- DM provider interface (one abstraction, multiple implementations)
- Voice integration via existing `PromptTemplate`
- Acceptance detection
- Enrichment phase
- DM generation, queuing, sending, reply handling
- Integration with existing `handle_replies` pattern

**Out of scope (deferred):**
- Choosing a specific DM API vendor (user will pick provider later)
- Browser automation for sends (we'll cross that bridge once API access is decided)
- Multi-account support
- Building a UI for review

---

## 2. Design principles

1. **Provider-agnostic.** The schema, prompt-builder, queue, and conversation logic do not know whether DMs are sent via browser, Unipile, official API, or human-assisted. Provider is a configurable adapter behind a single interface.

2. **Reuse existing Paperklip patterns, don't fork them.** Voice via `PromptTemplate`. Cost tracking via `AIUsageLog`. Reply pattern via `handle_replies`. Conversation memory via Sprint 6 `conversation` service. We add channel, not pipeline.

3. **Capture enrichment once, use it forever.** The data we collect from a profile post-acceptance is reusable across the first DM, follow-up DMs, future email re-engagement, and call scripts. Store it well.

4. **Enrich at the right time.** Discovery captures minimum-viable. Full enrichment happens AFTER acceptance, when LinkedIn shows us more data (1st-degree visibility) and the prospect is worth the cost.

5. **Two LinkedIn surfaces, one mental model.** Inbound DM ≈ inbound email. The same `handle_replies` worker handles both, parameterized by channel.

---

## 3. The four phases

```
   ┌──────────────────────────────────────────────────────────────────┐
   │   Discovery    →   Connect    →   Enrich    →   DM   →   Reply   │
   │   (done)           (done)         (NEW)       (NEW)    (NEW)     │
   └──────────────────────────────────────────────────────────────────┘
        run nightly      run daily      run on        when           on each
        on Mac           on Mac         acceptance    enriched       inbound
                                                     +scheduled
```

| Phase | Trigger | Action | What's captured |
|---|---|---|---|
| Discovery | Cron | Find LinkedIn company + decision-maker | `person_url`, `person_name`, `person_title` |
| Connect | Cron | Send connection request, no note | `connection_status='invited'` |
| **Enrich** | Acceptance detected | Load profile, capture rich context | Headline, About, posts, mutuals, BNI |
| **DM** | Enriched & scheduled | Generate via Claude, send via provider | `dm_thread_id`, body, sent_at |
| **Reply** | Inbound DM detected | Same pattern as email - Claude reply | Classification, reply body |

---

## 4. Data model

The LinkedIn data lives **in Paperklip's Postgres**, not in `linkedin_automation/`'s SQLite. The SQLite DB stays as the operational tracker for the browser-side bot (discovery + connect + enrichment); enrichment results are synced into Paperklip via a thin bridge command.

### 4.1 `LinkedInProfile` (one-per-Prospect)

```python
class LinkedInProfile(models.Model):
    prospect = models.OneToOneField(Prospect, on_delete=models.CASCADE, related_name='linkedin')

    # Identity (captured during discovery)
    person_url = models.URLField(unique=True)
    person_urn = models.CharField(max_length=120, blank=True, db_index=True,
        help_text="LinkedIn's stable internal ID, e.g. urn:li:person:abc123. Survives slug changes.")
    person_name = models.CharField(max_length=200)
    person_title = models.CharField(max_length=300, blank=True)

    company_url = models.URLField(blank=True)
    company_urn = models.CharField(max_length=120, blank=True, db_index=True)

    # Connection state machine
    CONNECTION_STATES = [
        ('not_connected', 'Not Connected'),
        ('invited', 'Invitation Sent'),
        ('accepted', 'Connected'),
        ('declined', 'Invitation Declined'),
        ('withdrawn', 'Invitation Withdrawn'),
        ('blocked', 'Blocked or Restricted'),
    ]
    connection_status = models.CharField(max_length=20, choices=CONNECTION_STATES, default='not_connected')
    invite_sent_at = models.DateTimeField(null=True, blank=True)
    connection_accepted_at = models.DateTimeField(null=True, blank=True)

    # Enrichment payload - JSON so we don't have to migrate every time we add a field
    enriched_at = models.DateTimeField(null=True, blank=True)
    enrichment_version = models.IntegerField(default=0,
        help_text="Bumps when we re-enrich. Lets us detect stale profiles.")
    enrichment_data = models.JSONField(default=dict, blank=True)
    # enrichment_data shape (documented but not enforced):
    # {
    #   "headline": "Owner at Brandit Promotional Products",
    #   "about_text": "...",
    #   "location": "Dublin, Ireland",
    #   "current_position_started": "2018-03",
    #   "tenure_months": 86,
    #   "open_to_work": false,
    #   "is_premium": true,
    #   "is_hiring": false,
    #   "profile_photo_url": "...",
    #   "recent_activity": [
    #     {"url": "...", "posted_at": "2026-05-10", "text": "...", "type": "post",
    #      "reactions": 47, "comments": 8, "topic": "industry_news"},
    #     ...
    #   ],
    #   "mutual_connections": [
    #     {"name": "Paul Rivers", "url": "...", "shared_via": "BNI Dublin"},
    #     ...
    #   ],
    #   "shared_communities": ["BNI Dublin Chapter X", "Promotional Products Ireland"],
    #   "skills": ["Embroidery", "Screen Printing"],
    #   "industry_signals": ["recently_promoted", "milestone_anniversary"]
    # }

    # Personalization hooks - extracted by Claude from enrichment_data
    # These are the fields the prompt-builder reads when writing a DM.
    hook_recent_post = models.TextField(blank=True,
        help_text="Best post we can reference: 'Saw your post on X — really resonated'")
    hook_mutual_connection = models.CharField(max_length=300, blank=True,
        help_text="Strongest mutual: 'Paul Rivers and I both know you from BNI'")
    hook_shared_community = models.CharField(max_length=200, blank=True,
        help_text="BNI/alumni/industry group: 'Fellow BNI Dublin member'")
    hook_company_signal = models.CharField(max_length=300, blank=True,
        help_text="Hiring, award, anniversary, expansion: 'Saw Brandit just hit 5 years'")
    hook_extracted_at = models.DateTimeField(null=True, blank=True)

    # DM tracking
    first_dm_thread_id = models.CharField(max_length=120, blank=True,
        help_text="LinkedIn's conversation/thread ID for the first DM thread.")
    first_dm_sent_at = models.DateTimeField(null=True, blank=True)
    first_dm_body = models.TextField(blank=True)
    last_outbound_dm_at = models.DateTimeField(null=True, blank=True)
    last_inbound_dm_at = models.DateTimeField(null=True, blank=True)

    # Provenance
    provider = models.CharField(max_length=40, blank=True,
        help_text="Which provider sent/observed this profile: browser_v1, unipile, official, manual")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'linkedin_profiles'
        indexes = [
            models.Index(fields=['connection_status', 'enriched_at']),
            models.Index(fields=['connection_status', 'first_dm_sent_at']),
        ]
```

### 4.2 `LinkedInMessage` (one-per-DM, both directions)

Mirrors `EmailLog` + `InboundEmail` combined.

```python
class LinkedInMessage(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='linkedin_messages')
    profile = models.ForeignKey(LinkedInProfile, on_delete=models.CASCADE, related_name='messages')

    DIRECTIONS = [('outbound', 'Outbound'), ('inbound', 'Inbound')]
    direction = models.CharField(max_length=10, choices=DIRECTIONS)

    # LinkedIn identifiers - what the provider gives us, normalized
    thread_id = models.CharField(max_length=120, db_index=True,
        help_text="Conversation ID. Same for all messages in a thread.")
    message_urn = models.CharField(max_length=200, blank=True, db_index=True,
        help_text="Provider's unique message ID. Unique within the provider.")

    body = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # For first-touch identification (the DM that opens the relationship)
    is_first_touch = models.BooleanField(default=False)

    # Inbound-only fields
    classified_as = models.CharField(max_length=30, blank=True,
        help_text="interested|objection|not_interested|question|silence|other")
    needs_reply = models.BooleanField(default=False)
    classified_at = models.DateTimeField(null=True, blank=True)

    # Reply tracking (when this inbound was replied to)
    replied_at = models.DateTimeField(null=True, blank=True)
    replied_with = models.ForeignKey('self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reply_to')

    # AI generation provenance for outbound DMs
    prompt_template = models.ForeignKey(PromptTemplate, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='linkedin_messages')
    ai_usage = models.ForeignKey('AIUsageLog', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='linkedin_messages')

    provider = models.CharField(max_length=40,
        help_text="Which provider delivered this: browser_v1, unipile, official, manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'linkedin_messages'
        indexes = [
            models.Index(fields=['thread_id', 'sent_at']),
            models.Index(fields=['direction', 'needs_reply']),
            models.Index(fields=['prospect', 'sent_at']),
        ]
        unique_together = [('provider', 'message_urn')]  # Idempotent ingestion
```

### 4.3 `LinkedInDMQueue` (outbound scheduling)

Why a queue table and not "just send when ready"? Three reasons:

1. **Rate-limit decoupling.** AI generation can run hourly (cheap, fast). Send-rate is constrained to ~20-30 DMs/day. Queue absorbs the mismatch.
2. **Provider failover.** If browser provider fails, we can retry with a different provider without re-running Claude.
3. **Audit + manual override.** Prakash can inspect a queued DM body before it ships. "Approve and send" workflow becomes one column.

```python
class LinkedInDMQueue(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='linkedin_dm_queue')
    profile = models.ForeignKey(LinkedInProfile, on_delete=models.CASCADE, related_name='dm_queue')

    STATES = [
        ('pending_generation', 'Pending AI Generation'),
        ('ready', 'Ready to Send'),
        ('approved', 'Approved (if manual approval gate enabled)'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=30, choices=STATES, default='pending_generation')

    # What kind of message and what voice
    KINDS = [('first_touch', 'First Touch'), ('follow_up', 'Follow-up'), ('reply', 'Reply to Inbound')]
    kind = models.CharField(max_length=20, choices=KINDS)
    prompt_template = models.ForeignKey(PromptTemplate, on_delete=models.PROTECT,
        related_name='dm_queue_items')
    in_reply_to = models.ForeignKey(LinkedInMessage, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='queued_replies')

    # Body lifecycle: generated → sent
    generated_body = models.TextField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    sent_message = models.OneToOneField(LinkedInMessage, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='source_queue_item')

    # Scheduling
    scheduled_for = models.DateTimeField(db_index=True,
        help_text="Earliest time this can be sent. Used to spread sends across day.")
    requires_approval = models.BooleanField(default=False,
        help_text="If True, send is blocked until Prakash approves via dashboard.")

    # Retry policy
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    last_error = models.TextField(blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'linkedin_dm_queue'
        indexes = [
            models.Index(fields=['status', 'scheduled_for']),
            models.Index(fields=['prospect', 'kind']),
        ]
```

### 4.4 Extension to `PromptTemplate.FEATURE_CHOICES`

```python
FEATURE_CHOICES = [
    ('email_reply', 'Email Reply Generation'),         # existing
    ('call_analysis', 'Call Transcript Analysis'),     # existing
    ('script_improvement', 'Script Improvement'),      # existing
    ('classification', 'Email Classification'),        # existing
    ('linkedin_first_touch', 'LinkedIn First DM'),     # NEW
    ('linkedin_reply', 'LinkedIn Reply Generation'),   # NEW
    ('linkedin_classification', 'LinkedIn Inbound Classification'),  # NEW
    ('linkedin_enrichment_extraction', 'Extract Personalization Hooks'),  # NEW
]
```

No new persona table. TaggIQ's LinkedIn voice is **a second row in `prompt_templates`** with `feature='linkedin_first_touch'`. Same pattern as adding TaggIQ vs FP for email.

---

## 5. The Provider abstraction

A single Python protocol that every DM provider must implement. This is the boundary between **the rest of Paperklip** (which doesn't change when we swap providers) and **the actual sending mechanism** (browser today, API tomorrow).

```python
# campaigns/linkedin/provider_base.py
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime

@dataclass
class SendResult:
    ok: bool
    thread_id: str = ""
    message_urn: str = ""
    sent_at: datetime | None = None
    error_code: str = ""           # "blocked", "not_connected", "rate_limited", "unknown"
    error_detail: str = ""

@dataclass
class InboundDM:
    thread_id: str
    message_urn: str
    from_person_url: str
    from_person_urn: str
    body: str
    sent_at: datetime
    is_read: bool

@dataclass
class AcceptanceResult:
    person_urn: str
    person_url: str
    accepted_at: datetime | None

@dataclass
class EnrichmentResult:
    person_url: str
    headline: str
    about_text: str
    location: str
    tenure_months: int | None
    recent_activity: list[dict]
    mutual_connections: list[dict]
    shared_communities: list[str]
    raw: dict  # full payload, opaque to caller

class LinkedInDMProvider(Protocol):
    """All LinkedIn surface area sits behind this interface."""

    name: str  # "browser_v1" | "unipile" | "official" | "manual"

    def detect_accepted(self, pending_person_urns: list[str]) -> list[AcceptanceResult]:
        """Return URNs from the input list whose invites have been accepted."""
        ...

    def enrich(self, person_url: str) -> EnrichmentResult:
        """Fetch full profile for a connected person. Must be 1st-degree."""
        ...

    def send_dm(self, person_url: str, body: str) -> SendResult:
        """Send a DM. Returns provider's thread/message identifiers on success."""
        ...

    def list_inbound(self, since: datetime) -> list[InboundDM]:
        """Return new inbound DMs since the given timestamp."""
        ...

    def health_check(self) -> tuple[bool, str]:
        """Return (healthy, reason). Used to fail-fast cron jobs."""
        ...
```

Initial implementations (when we're ready to build them):

| Provider | When to use | Status |
|---|---|---|
| `BrowserDMProvider` | Default for v1, runs on Mac via undetected-chromedriver | Build first |
| `UnipileDMProvider` | Server-side, ~$50-100/mo, REST API | Build when Prakash signs up |
| `OfficialAPIDMProvider` | If LinkedIn Partner approval ever lands | Stub for now |
| `ManualDMProvider` | Fallback - writes DM to a "draft queue" Prakash sends manually | Build for emergency |
| `MockDMProvider` | Testing only | Build alongside provider interface |

Provider is selected per-Product via a new field on `ProductBrain` or a simple settings constant:

```python
# campaigns/linkedin/settings.py
PROVIDER_BY_PRODUCT = {
    'taggiq': 'browser_v1',
    'fullypromoted': 'browser_v1',
    'print-promo': 'browser_v1',
    'kritno': 'browser_v1',
}
```

When Unipile arrives: change the value, no code changes elsewhere.

---

## 6. The cron pipeline

Five new jobs. All run from EC2 except the two browser-dependent ones (acceptance + enrichment + browser-send) which run from Prakash's Mac until we move to Unipile.

```
┌──────────────────────────────────────────────────────────────────────┐
│  detect_accepted_connections     (Mac, browser)     daily 09:00      │
│  → polls /mynetwork/invitation-manager/sent/                         │
│  → flips LinkedInProfile.connection_status = 'accepted'              │
│  → queues enrichment task                                            │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  enrich_accepted_profiles       (Mac, browser)     daily 09:30      │
│  → for each accepted but not-yet-enriched profile                    │
│  → load profile + activity tab + posts                               │
│  → save enrichment_data JSON                                         │
│  → kick off hook_extraction                                          │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  extract_personalization_hooks  (EC2, Claude)      hourly *:15       │
│  → for each enriched but not-yet-hooked profile                      │
│  → Claude reads enrichment_data, picks best hooks                    │
│  → writes hook_recent_post / hook_mutual_connection / etc.           │
│  → queues first DM via LinkedInDMQueue (status=pending_generation)   │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  generate_dms                   (EC2, Claude)      hourly *:30       │
│  → for each queue item in 'pending_generation'                       │
│  → reuse send_ai_reply pattern: pull PromptTemplate, build prompt,   │
│    inject conversation context, call Claude, validate, store body   │
│  → status → 'ready' (or 'approved' if requires_approval=False)       │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  send_dms                       (Mac or EC2)       hourly *:45       │
│  → for each queue item in 'ready'/'approved' due to be sent          │
│  → enforce daily/weekly cap (20-30/day per account)                  │
│  → call provider.send_dm(person_url, body)                           │
│  → on success: create LinkedInMessage, mark queue 'sent'             │
│  → on failure: increment attempts, schedule retry, alert if blocked  │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  poll_linkedin_inbox            (Mac or EC2)       hourly *:55       │
│  → provider.list_inbound(since=last_poll_at)                         │
│  → for each new message: create LinkedInMessage(direction='inbound') │
│  → classify via Claude (linkedin_classification)                     │
│  → if needs_reply → queue a reply via LinkedInDMQueue                │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  handle_replies (existing pattern, parameterized by channel)         │
│  → process LinkedInDMQueue items with kind='reply'                   │
│  → same Claude → validate → provider.send_dm flow                    │
└──────────────────────────────────────────────────────────────────────┘
```

Note the cleanliness: `handle_replies` already knows how to drive Claude over email replies. The reply path through LinkedIn reuses that same orchestrator — just a different input source (`LinkedInDMQueue` instead of `InboundEmail.needs_reply`) and a different send method (`provider.send_dm` instead of SMTP).

---

## 7. Voice integration (concrete example)

When a TaggIQ prospect "Sharon Bates from Keynote Marketing" accepts our invite, the flow:

1. **Enrichment** captures her: 12 years at Keynote, BNI Wexford chapter, recent post about embroidery automation.

2. **Hook extraction** (Claude on EC2) reads enrichment_data and writes:
   - `hook_shared_community = "Fellow BNI member (Wexford chapter)"`
   - `hook_recent_post = "Saw your post about embroidery automation — really practical"`
   - `hook_company_signal = "12 years at Keynote — solid run"`

3. **DM generation** queries:
   ```python
   PromptTemplate.objects.get(
       product=taggiq,
       feature='linkedin_first_touch',
       is_active=True,
   )
   ```
   This template has TaggIQ voice rules + LinkedIn-specific constraints (max 300 chars, casual, no signature).

4. **Prompt builder** assembles:
   ```
   <system prompt from PromptTemplate>
   
   <conversation history from ConversationService>
     Email history: 3 emails sent (TaggIQ BNI Promo Global), no reply
     Call history: 1 call, didn't connect
   
   <person context>
     Name: Sharon Bates
     Title: Owner, Keynote Marketing
     Hooks:
       - Fellow BNI member (Wexford chapter)
       - Saw your post about embroidery automation — really practical
       - 12 years at Keynote — solid run
   
   <task>
     Write a first LinkedIn DM. Use at most ONE hook (the strongest).
     Casual, conversational. No pitch. 60-120 words max.
   ```

5. **Claude generates:**
   > "Thanks for connecting Sharon — saw your post on embroidery automation, totally agree on the bottleneck around small runs. Fellow BNI member here (Wexford chapter via Paul Rivers). Curious if you've looked at any quote-to-decorate workflow tooling? Happy to share what we've built for shops your size if it's useful."

6. **Validation** (reuse existing reply audit): length OK, no price commitments, no em dashes, no "just say the word".

7. **Send via provider:** `BrowserDMProvider.send_dm(sharon_profile_url, body)` → creates `LinkedInMessage`, marks queue as sent.

The same machinery serves TaggIQ, FP Franchise (Prakash voice), FP Dublin B2B (Emma voice), and Kritno when it launches. Adding a product = one PromptTemplate row.

---

## 8. Conversation continuity (the contextual marketing thesis)

This is where Paperklip's value proposition crystallizes. When Sharon replies to the LinkedIn DM, the reply-handling pipeline:

1. Reads inbound DM
2. Calls `ConversationService.get_full_context(prospect=sharon)` — returns:
   - All emails sent/received (in order)
   - All calls placed (with transcript snippets)
   - All LinkedIn DMs in this thread
   - Profile enrichment snapshot
3. Passes everything to Claude when generating the reply

The AI sees **the entire relationship**, not just the LinkedIn thread. If Sharon mentioned in email three months ago that she's interested in webstore decoration, the LinkedIn reply can pick that up.

This is Sprint 6 Phase 2A's `conversation` service. It already exists (per CLAUDE.md). LinkedIn just adds a new channel to feed it.

---

## 9. Acceptance detection — the only must-build-now piece

Until API access arrives, acceptance detection is browser-based and runs from Mac. It's the one thing we need before the API decision matters, because **we can't know who to enrich until we know who accepted.**

Two complementary signals:

**Signal A: invitation-manager/sent/ delta**
- Visit `/mynetwork/invitation-manager/sent/`
- Page lists pending invites. Compare URNs against `LinkedInProfile.connection_status='invited'` rows.
- Missing from the page = either accepted OR withdrawn by us. To disambiguate, visit profile once: see Connect button (declined/expired) vs Message button (accepted).

**Signal B: /mynetwork/ recent connections**
- Visit `/mynetwork/`
- Walk the "Recent Connections" list (LinkedIn shows newest first)
- Anyone whose URN matches a `LinkedInProfile.connection_status='invited'` → flip to `'accepted'`

Both are read-only, cheap, low-detection-risk.

Frequency: once per day. Acceptance lag of 12-24h is fine for B2B outbound.

Implementation: `linkedin_automation/acceptance.py` (new file), called by a new CLI command `cli detect-accepted`.

---

## 10. Enrichment — what we capture and why

The enrichment payload (`LinkedInProfile.enrichment_data`) is the data foundation for personalization. We capture it in one pass post-acceptance because:

- 1st-degree connections see fuller profiles (more posts, more activity)
- It's the natural moment to visit (people check their new connections' profiles all the time)
- Doing it later wastes another visit; doing it earlier (during discovery) wastes work on people who never accept

| Field | Source | Used for |
|---|---|---|
| `headline` | Profile header | Sanity check title accuracy |
| `about_text` | About section | Hook extraction — what they care about |
| `location` | Profile header | Voice matching (Dublin vs London tone) |
| `current_position_started` | Experience section | Tenure hook ("8 years at...") |
| `tenure_months` | Computed from started | Hook generation |
| `is_premium` | Profile badges | DM length budget (Premium → longer DMs OK) |
| `is_hiring` | "Hiring" indicator | Sales hook (TaggIQ growth pitch) |
| `recent_activity[]` | Activity tab, last 5 items | Most useful hook — references specific content |
| `mutual_connections[]` | "X mutual" hover | Trust hook — "Paul Rivers and I both know you" |
| `shared_communities[]` | Activity + experience | BNI chapter, alumni group, industry association |
| `industry_signals[]` | Derived | Promoted, anniversary, award, expansion |

The `enrichment_data` JSON shape is documented (not enforced) so providers can extend without schema migrations. The `hook_*` columns are the **enforced contract** the prompt-builder reads — they're plain strings, easy to inspect in the admin, easy to override manually.

---

## 11. What we do NOT build (yet, on purpose)

1. **No multi-account orchestration.** One account, Prakash's. If we ever need 2 accounts (Lisa + Prakash), the schema already allows it (sessions table has session_type, can add account_id).

2. **No automated InMail.** Even when Premium is purchased, InMail to non-connections is a different surface with different rate limits. Out of scope.

3. **No Sales Navigator integration.** SN's API is closed; its filters are useful but UI-only. If Prakash decides SN is worth $80/mo for filter quality during discovery, we add it as a separate discovery_provider, not a DM provider.

4. **No DM template library.** All DMs go through Claude generation against PromptTemplate. We don't maintain a stock of canned messages — voice is one source of truth.

5. **No A/B testing of DM variants.** Single prompt template per product per feature for v1. A/B comes later when we have volume to draw conclusions.

6. **No automatic follow-up cadences.** If no reply, no follow-up DM by default. A "follow-up in 14 days" cadence is straightforward to add later (it's just another `LinkedInDMQueue` row with `kind='follow_up'`).

7. **No UI for review queue.** The Django admin handles `LinkedInDMQueue` with `requires_approval=True`. A purpose-built dashboard is a v2 polish item.

---

## 12. Implementation phases

| Phase | Goal | Build | Status |
|---|---|---|---|
| **0** | Foundation already in place | `linkedin_automation/` discovery + connect | DONE |
| **1** | Schema + provider interface | Models, migrations, Protocol, MockProvider, ManualProvider | NEXT |
| **2** | Acceptance + enrichment | Browser-based `acceptance.py` + `enrichment.py` + Mac cron | After Phase 1 |
| **3** | Hook extraction (Claude) | `extract_hooks` management command, prompt template, EC2 cron | After Phase 2 |
| **4** | DM generation + queue | `generate_dms` command, queue model integration | After Phase 3 |
| **5** | Provider: BrowserDM | `BrowserDMProvider` impl using Selenium, send-side throttling | After Phase 4 |
| **6** | Inbound polling + reply | `poll_inbox` + reuse `handle_replies` orchestration | After Phase 5 |
| **7** | Pilot: 10 IE prospects | Manual approval gate ON. Validate every DM. | Sign-off gate |
| **8** | Full IE rollout | Approval gate OFF for first DMs. Reply DMs always approved by Claude. | Production |
| **9** | UK rollout | Same code, more data | After IE |
| **10** | Provider swap | When Prakash gets API access, implement provider, flip flag | Open-ended |

---

## 13. The provider-swap moment

This is what we're optimizing for. When API access arrives:

```python
# campaigns/linkedin/settings.py — change ONE line per product
PROVIDER_BY_PRODUCT = {
    'taggiq': 'unipile',  # was 'browser_v1'
    ...
}
```

And implement:

```python
# campaigns/linkedin/providers/unipile.py
class UnipileDMProvider(LinkedInDMProvider):
    name = "unipile"

    def __init__(self):
        self.client = unipile.Client(api_key=settings.UNIPILE_API_KEY)

    def send_dm(self, person_url, body):
        response = self.client.messages.create(recipient=person_url, body=body)
        return SendResult(
            ok=True, thread_id=response.thread_id,
            message_urn=response.id, sent_at=response.sent_at,
        )

    def detect_accepted(self, urns): ...
    def enrich(self, url): ...
    def list_inbound(self, since): ...
    def health_check(self): ...
```

That's it. No changes to:
- Schema
- Cron jobs
- Prompt templates
- Conversation service
- Reply pipeline
- `handle_replies`

If we did our job here, Phase 10 is one file (~200 lines) and a config flip.

---

## 14. Risks specific to DM phase

| Risk | Mitigation |
|---|---|
| LinkedIn detects DM spray pattern | 20-30 DMs/day cap, randomized scheduling, per-product cap, kill switch on first warning |
| Browser-based DM is fragile (DOM changes) | Provider abstraction means we can switch to API quickly when ready |
| Wrong hook extracted → bad personalization | Hooks pass through Claude audit step; humans can override `hook_*` columns in admin |
| DM looks AI-generated | Voice rules in PromptTemplate enforce conversational tone; length cap 60-120 words; no signature on LinkedIn |
| Enrichment captures stale data | `enriched_at` + `enrichment_version` allow re-enrichment cron (monthly) |
| Cross-channel attribution gets messy | All channels write to `ProspectEvent` (Sprint 8) — single audit trail |
| One Prakash account = single point of failure | Daily health checks; immediate stop on 429; quarterly review of account health |

---

## 15. Definition of done

For the design to be considered complete enough to start implementation:

- [x] Data model defined with examples
- [x] Provider abstraction defined with interface
- [x] Voice integration uses existing PromptTemplate (no parallel infrastructure)
- [x] Reply flow reuses existing `handle_replies` pattern
- [x] Phased plan with clear sign-off gates
- [x] Risks named and mitigated
- [x] API-access decision is a config flip, not a refactor

For Phase 1 to be considered complete:

- [ ] Migrations applied on local + EC2
- [ ] `LinkedInDMProvider` protocol checked in
- [ ] `ManualDMProvider` (writes to draft queue, no send) implemented
- [ ] `MockDMProvider` for tests implemented
- [ ] Bridge command: `linkedin_automation` SQLite → Paperklip `LinkedInProfile` row sync
- [ ] Admin pages for `LinkedInProfile`, `LinkedInMessage`, `LinkedInDMQueue` registered

---

## 16. Open question for Prakash

Before implementation starts:

**Approval gate default for first DMs: ON or OFF?**

- ON: Every first DM lands in `LinkedInDMQueue` with `requires_approval=True`. You review and click send in Django admin. Slower, zero blast radius.
- OFF: Claude generates → sends. Trust the prompt template + audit detectors.

Recommendation: **ON for the first 20 DMs per product**, then auto-flip to OFF once we've validated tone. Easy to wire: `Product.linkedin_auto_approve_after_n` field.

Reply DMs: always automatic. The reply pattern is identical to email, which already runs unsupervised on EC2.
