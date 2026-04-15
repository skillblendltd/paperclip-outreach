"""H1 — Prospect reply counters (2026-04-15).

Adds two counter fields to `Prospect`:

  - `last_replied_at` DateTimeField(null=True, blank=True)
  - `reply_count` IntegerField(default=0)

Fixes a silent bug: four code paths already read
`getattr(prospect, 'reply_count', 0)` expecting a counter field on
`Prospect` (rules_engine.should_escalate, send_ai_reply Phase 7.2.6,
next_action trigger payload, seed_sprint7_brains fixtures). Before
this migration, all four consumers silently returned 0, making the
Sprint 7 brain `escalation_rules.on_reply_count_gte` thresholds
(2, 4, 4) unreachable.

## Backfill

Per CTO review: includes a forward-only `RunPython` data migration
that populates the two new fields from aggregates of existing
`InboundEmail` rows. Backfill counts only the same classifications
the live write site counts (interested, question, other,
not_interested, opt_out), so historical counters match the policy
the pipeline will use going forward. Without the backfill, the first
week of escalation thresholds would under-fire for prospects with
pre-fix reply history.

The backfill is idempotent and safe to re-run.

## Deferred index

No DB index on `(campaign_id, last_replied_at)` today. At current
scale (~7K prospects total, largest single campaign 999 rows),
`ORDER BY last_replied_at DESC` is sub-millisecond unindexed. Add
the index when an admin or KPI query first shows latency — not
before. Premature indexing carries write amplification with no
observable benefit at this scale.

## Migration safety

Additive only. No rename, no type change, no constraint change on
existing columns. Rollback is trivial: `migrate campaigns 0019`
drops both columns.
"""
from django.db import migrations, models
from django.db.models import Count, Max, Q


def backfill_reply_counters(apps, schema_editor):
    """Populate reply_count and last_replied_at from InboundEmail aggregates.

    Matches the live-write policy in check_replies._process_mailbox:
    counts inbounds with classification in the eligible set, excludes
    bounce / out_of_office. Iterates with .iterator() to avoid
    loading every Prospect into memory at once on large deployments.
    """
    Prospect = apps.get_model('campaigns', 'Prospect')

    COUNTED = ('interested', 'question', 'other', 'not_interested', 'opt_out')

    counted_filter = Q(inbound_emails__classification__in=COUNTED)

    qs = Prospect.objects.annotate(
        _rcount=Count('inbound_emails', filter=counted_filter),
        _last=Max('inbound_emails__created_at', filter=counted_filter),
    ).only('id')

    updated = 0
    for row in qs.iterator():
        Prospect.objects.filter(pk=row.pk).update(
            reply_count=row._rcount or 0,
            last_replied_at=row._last,
        )
        updated += 1
    print(f'  [0020 backfill] updated {updated} prospect row(s)')


def unbackfill(apps, schema_editor):
    """Reverse direction — zero the counters. Used only on migrate backward.

    Harmless even without this because a backward migration drops both
    columns entirely in AddField's auto-reverse. Kept as a no-op so the
    `RunPython` pair is explicit about its reversibility.
    """
    Prospect = apps.get_model('campaigns', 'Prospect')
    Prospect.objects.all().update(reply_count=0, last_replied_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0019_campaign_reply_window'),
    ]

    operations = [
        migrations.AddField(
            model_name='prospect',
            name='reply_count',
            field=models.IntegerField(
                default=0,
                help_text='Number of real human replies received from this '
                          'prospect. Written by check_replies atomic F() '
                          'increment. Counts interested/question/other/'
                          'not_interested/opt_out. Excludes bounce, '
                          'out_of_office, system-denylist (DocuSign, etc).',
            ),
        ),
        migrations.AddField(
            model_name='prospect',
            name='last_replied_at',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text='Most recent moment this prospect replied (capture '
                          'time, not the email Date header). Used for '
                          '"recent activity" sorting and KPI rollups.',
            ),
        ),
        migrations.RunPython(backfill_reply_counters, unbackfill),
    ]
