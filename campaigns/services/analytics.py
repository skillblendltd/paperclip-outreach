"""
Read-only analytics service for pipeline KPIs.

All functions return plain dicts (JSON-serializable).
Never mutates data. All queries go through Django ORM.

Sprint 9 - Observability & Analytics Dashboard.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from campaigns.models import (
    AIUsageLog, CallLog, Campaign, EmailLog, InboundEmail,
    Prospect, ProspectEvent, Suppression,
)


def _product_filter(qs, product_slug, field='campaign__product_ref__slug'):
    """Apply optional product filter to a queryset."""
    if product_slug:
        return qs.filter(**{field: product_slug})
    return qs


def _period_filter(qs, days, field='created_at'):
    """Apply date range filter to a queryset."""
    cutoff = timezone.now() - timedelta(days=days)
    return qs.filter(**{f'{field}__gte': cutoff})


def get_pipeline_kpis(product_slug=None, days=7):
    """Master KPI endpoint - all key numbers in one call."""
    now = timezone.now()
    cutoff = now - timedelta(days=days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # --- Email metrics ---
    email_qs = EmailLog.objects.filter(status='sent')
    email_qs = _product_filter(email_qs, product_slug)

    sent_period = email_qs.filter(created_at__gte=cutoff).count()
    sent_today = email_qs.filter(created_at__gte=today_start).count()

    reply_qs = InboundEmail.objects.all()
    reply_qs = _product_filter(reply_qs, product_slug)

    replies_period = reply_qs.filter(received_at__gte=cutoff).count()
    auto_replied = reply_qs.filter(
        received_at__gte=cutoff, auto_replied=True
    ).count()
    pending_reply = reply_qs.filter(
        needs_reply=True, replied=False
    ).count()

    # Avg response time for auto-replied emails (minutes)
    responded = reply_qs.filter(
        auto_replied=True,
        reply_sent_at__isnull=False,
        received_at__isnull=False,
        received_at__gte=cutoff,
    )
    avg_response = None
    if responded.exists():
        durations = [
            (r.reply_sent_at - r.received_at).total_seconds() / 60
            for r in responded
            if r.reply_sent_at and r.received_at
        ]
        if durations:
            avg_response = round(sum(durations) / len(durations), 1)

    reply_rate = round(replies_period / sent_period * 100, 1) if sent_period else 0.0

    # --- Call metrics ---
    call_qs = CallLog.objects.all()
    call_qs = _product_filter(call_qs, product_slug)

    calls_period = call_qs.filter(created_at__gte=cutoff).count()
    calls_answered = call_qs.filter(
        created_at__gte=cutoff, status='answered'
    ).count()
    answer_rate = round(calls_answered / calls_period * 100, 1) if calls_period else 0.0
    demos_from_calls = call_qs.filter(
        created_at__gte=cutoff, disposition='demo_booked'
    ).count()

    # --- Funnel snapshot (current state, not period-based) ---
    prospect_qs = Prospect.objects.all()
    prospect_qs = _product_filter(prospect_qs, product_slug)

    funnel = {}
    for status_code, _ in Prospect.STATUS_CHOICES:
        count = prospect_qs.filter(status=status_code).count()
        if count > 0:
            funnel[status_code] = count

    # --- Velocity (transitions in period) ---
    event_qs = ProspectEvent.objects.filter(created_at__gte=cutoff)
    if product_slug:
        event_qs = event_qs.filter(prospect__campaign__product_ref__slug=product_slug)

    velocity = {
        'new_to_contacted': event_qs.filter(
            from_status='new', to_status='contacted'
        ).count(),
        'contacted_to_interested': event_qs.filter(
            from_status='contacted', to_status='interested'
        ).count(),
        'interested_to_demo': event_qs.filter(
            from_status='interested', to_status='demo_scheduled'
        ).count(),
    }

    # --- AI cost ---
    ai_qs = AIUsageLog.objects.all()
    ai_qs = _product_filter(ai_qs, product_slug, field='product__slug')

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cost_mtd = ai_qs.filter(
        created_at__gte=month_start
    ).aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

    cost_period = ai_qs.filter(
        created_at__gte=cutoff
    ).aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

    replies_generated = ai_qs.filter(
        created_at__gte=cutoff, feature='email_reply', success=True
    ).count()

    demos_total = prospect_qs.filter(status='demo_scheduled').count()
    cost_per_demo = round(float(cost_mtd) / demos_total, 2) if demos_total else None

    # --- Health ---
    stuck_cutoff = now - timedelta(days=7)
    stuck = prospect_qs.filter(
        status='interested',
        updated_at__lte=stuck_cutoff,
    ).count()

    pending_gt2h = reply_qs.filter(
        needs_reply=True,
        replied=False,
        received_at__lte=now - timedelta(hours=2),
    ).count()

    last_send = EmailLog.objects.filter(status='sent').order_by('-created_at').first()
    last_reply_check = InboundEmail.objects.order_by('-created_at').first()

    return {
        'period': {
            'from': cutoff.date().isoformat(),
            'to': now.date().isoformat(),
            'days': days,
        },
        'email': {
            'sent': sent_period,
            'sent_today': sent_today,
            'replies_received': replies_period,
            'reply_rate_pct': reply_rate,
            'auto_replied': auto_replied,
            'pending_reply': pending_reply,
            'avg_response_minutes': avg_response,
        },
        'calls': {
            'placed': calls_period,
            'answered': calls_answered,
            'answer_rate_pct': answer_rate,
            'demos_from_calls': demos_from_calls,
        },
        'funnel': funnel,
        'velocity': velocity,
        'ai': {
            'cost_mtd_usd': float(cost_mtd),
            'cost_period_usd': float(cost_period),
            'replies_generated': replies_generated,
            'cost_per_demo': cost_per_demo,
        },
        'health': {
            'stuck_interested_gt7d': stuck,
            'pending_replies_gt2h': pending_gt2h,
            'last_send_at': last_send.created_at.isoformat() if last_send else None,
            'last_reply_check_at': last_reply_check.created_at.isoformat() if last_reply_check else None,
        },
    }


def get_funnel_transitions(product_slug=None, days=30):
    """ProspectEvent transitions aggregated with avg timing."""
    cutoff = timezone.now() - timedelta(days=days)

    event_qs = ProspectEvent.objects.filter(created_at__gte=cutoff)
    if product_slug:
        event_qs = event_qs.filter(prospect__campaign__product_ref__slug=product_slug)

    # Aggregate transitions
    transitions_raw = (
        event_qs
        .values('from_status', 'to_status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    transitions = []
    for t in transitions_raw:
        # Calculate avg days between transitions for this pair
        events = event_qs.filter(
            from_status=t['from_status'],
            to_status=t['to_status'],
        ).select_related('prospect')

        avg_days = None
        day_diffs = []
        for e in events:
            # Find previous event for this prospect to calculate time between
            prev = ProspectEvent.objects.filter(
                prospect=e.prospect,
                to_status=e.from_status,
                created_at__lt=e.created_at,
            ).order_by('-created_at').first()
            if prev:
                diff = (e.created_at - prev.created_at).total_seconds() / 86400
                day_diffs.append(diff)

        if day_diffs:
            avg_days = round(sum(day_diffs) / len(day_diffs), 1)

        transitions.append({
            'from_status': t['from_status'],
            'to_status': t['to_status'],
            'count': t['count'],
            'avg_days': avg_days,
        })

    # Win/loss from interested
    from_interested_to_demo = event_qs.filter(
        from_status='interested', to_status='demo_scheduled'
    ).count()
    from_interested_to_lost = event_qs.filter(
        from_status='interested', to_status__in=['not_interested', 'opted_out']
    ).count()
    total_from_interested = from_interested_to_demo + from_interested_to_lost
    win_rate = round(
        from_interested_to_demo / total_from_interested * 100, 1
    ) if total_from_interested else 0.0

    return {
        'transitions': transitions,
        'win_loss': {
            'from_interested_to_demo': from_interested_to_demo,
            'from_interested_to_lost': from_interested_to_lost,
            'win_rate_pct': win_rate,
        },
    }


def get_daily_trends(product_slug=None, days=14):
    """Daily rollups for time series charts."""
    cutoff = timezone.now() - timedelta(days=days)

    # Emails sent per day
    email_qs = EmailLog.objects.filter(status='sent', created_at__gte=cutoff)
    email_qs = _product_filter(email_qs, product_slug)
    emails_by_day = dict(
        email_qs
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )

    # Replies per day
    reply_qs = InboundEmail.objects.filter(received_at__gte=cutoff)
    reply_qs = _product_filter(reply_qs, product_slug)
    replies_by_day = dict(
        reply_qs
        .annotate(date=TruncDate('received_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )

    # Interested transitions per day
    event_qs = ProspectEvent.objects.filter(
        to_status='interested', created_at__gte=cutoff
    )
    if product_slug:
        event_qs = event_qs.filter(prospect__campaign__product_ref__slug=product_slug)
    interested_by_day = dict(
        event_qs
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )

    # Demos per day
    demo_qs = ProspectEvent.objects.filter(
        to_status='demo_scheduled', created_at__gte=cutoff
    )
    if product_slug:
        demo_qs = demo_qs.filter(prospect__campaign__product_ref__slug=product_slug)
    demos_by_day = dict(
        demo_qs
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .values_list('date', 'count')
    )

    # AI cost per day
    ai_qs = AIUsageLog.objects.filter(created_at__gte=cutoff)
    ai_qs = _product_filter(ai_qs, product_slug, field='product__slug')
    cost_by_day = dict(
        ai_qs
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(total=Sum('cost_usd'))
        .values_list('date', 'total')
    )

    # Build series
    series = []
    current = cutoff.date()
    end = timezone.now().date()
    while current <= end:
        series.append({
            'date': current.isoformat(),
            'emails_sent': emails_by_day.get(current, 0),
            'replies': replies_by_day.get(current, 0),
            'interested': interested_by_day.get(current, 0),
            'demos': demos_by_day.get(current, 0),
            'ai_cost_usd': float(cost_by_day.get(current, Decimal('0'))),
        })
        current += timedelta(days=1)

    return {'series': series}


def get_campaign_rankings(product_slug=None, days=30):
    """Campaigns ranked by reply rate, with per-sequence breakdown."""
    cutoff = timezone.now() - timedelta(days=days)

    campaigns = Campaign.objects.filter(sending_enabled=True)
    if product_slug:
        campaigns = campaigns.filter(product_ref__slug=product_slug)

    results = []
    for campaign in campaigns:
        prospects = campaign.prospect_set.count()
        emails_sent = EmailLog.objects.filter(
            campaign=campaign, status='sent', created_at__gte=cutoff
        ).count()
        replies = InboundEmail.objects.filter(
            campaign=campaign, received_at__gte=cutoff
        ).count()
        interested = campaign.prospect_set.filter(status='interested').count()
        demos = campaign.prospect_set.filter(status='demo_scheduled').count()

        reply_rate = round(replies / emails_sent * 100, 1) if emails_sent else 0.0
        conversion_rate = round(interested / prospects * 100, 1) if prospects else 0.0

        # Per-sequence breakdown
        seq_stats = []
        for seq_num in range(1, 6):
            seq_sent = EmailLog.objects.filter(
                campaign=campaign, status='sent',
                sequence_number=seq_num, created_at__gte=cutoff,
            ).count()
            if seq_sent == 0:
                continue

            # Count replies that came after this sequence
            seq_replies = InboundEmail.objects.filter(
                campaign=campaign,
                replied_to_sequence=seq_num,
                received_at__gte=cutoff,
            ).count()
            seq_rate = round(seq_replies / seq_sent * 100, 1) if seq_sent else 0.0
            seq_stats.append({
                'seq': seq_num,
                'sent': seq_sent,
                'replies': seq_replies,
                'reply_rate_pct': seq_rate,
            })

        results.append({
            'id': str(campaign.id),
            'name': campaign.name,
            'prospects': prospects,
            'emails_sent': emails_sent,
            'replies': replies,
            'reply_rate_pct': reply_rate,
            'interested': interested,
            'demos': demos,
            'conversion_rate_pct': conversion_rate,
            'sequence_stats': seq_stats,
        })

    # Sort by reply rate descending
    results.sort(key=lambda x: x['reply_rate_pct'], reverse=True)

    return {
        'campaigns': results,
        'ranked_by': 'reply_rate_pct',
    }


def get_action_items(product_slug=None):
    """Named action items: pending replies, cooling leads, upcoming demos, recent wins, alerts."""
    now = timezone.now()

    # --- Pending replies (with prospect names) ---
    pending_qs = InboundEmail.objects.filter(
        needs_reply=True, replied=False
    ).select_related('prospect', 'campaign').order_by('received_at')
    if product_slug:
        pending_qs = pending_qs.filter(campaign__product_ref__slug=product_slug)

    pending_replies = []
    for ie in pending_qs[:10]:
        hours = (now - ie.received_at).total_seconds() / 3600 if ie.received_at else 0
        pending_replies.append({
            'prospect_name': ie.prospect.decision_maker_name if ie.prospect else ie.from_name,
            'company': ie.prospect.business_name if ie.prospect else '',
            'hours_waiting': round(hours, 1),
            'subject': ie.subject[:60],
            'inbound_id': str(ie.id),
        })

    # --- Cooling leads (interested >7 days, no recent activity) ---
    cool_cutoff = now - timedelta(days=7)
    prospect_qs = Prospect.objects.filter(
        status='interested',
        updated_at__lte=cool_cutoff,
        send_enabled=True,
    ).select_related('campaign')
    if product_slug:
        prospect_qs = prospect_qs.filter(campaign__product_ref__slug=product_slug)

    cooling = []
    for p in prospect_qs.order_by('updated_at')[:10]:
        days_since = (now - p.updated_at).days
        cooling.append({
            'prospect_name': p.decision_maker_name,
            'company': p.business_name,
            'status': p.status,
            'days_since_touch': days_since,
            'campaign': p.campaign.name,
        })

    # --- Upcoming demos ---
    demo_qs = Prospect.objects.filter(
        status='demo_scheduled',
    ).select_related('campaign')
    if product_slug:
        demo_qs = demo_qs.filter(campaign__product_ref__slug=product_slug)

    demos = []
    for p in demo_qs[:10]:
        demos.append({
            'prospect_name': p.decision_maker_name,
            'company': p.business_name,
            'campaign': p.campaign.name,
        })

    # --- Recent wins (last 7 days status changes to positive outcomes) ---
    win_cutoff = now - timedelta(days=7)
    win_qs = ProspectEvent.objects.filter(
        created_at__gte=win_cutoff,
        to_status__in=['interested', 'demo_scheduled', 'design_partner', 'customer'],
    ).select_related('prospect').order_by('-created_at')
    if product_slug:
        win_qs = win_qs.filter(prospect__campaign__product_ref__slug=product_slug)

    wins = []
    for e in win_qs[:10]:
        wins.append({
            'prospect_name': e.prospect.decision_maker_name if e.prospect else '',
            'company': e.prospect.business_name if e.prospect else '',
            'to_status': e.to_status,
            'when': e.created_at.isoformat(),
            'triggered_by': e.triggered_by,
        })

    # --- System alerts ---
    alerts = []

    # Check for stuck replies
    stuck_replies = InboundEmail.objects.filter(
        needs_reply=True, replied=False,
        received_at__lte=now - timedelta(hours=6),
    ).count()
    if stuck_replies:
        alerts.append({
            'level': 'critical',
            'message': f'{stuck_replies} replies stuck >6hrs',
            'action': 'Check handle_replies logs: docker exec outreach_cron tail -50 /tmp/outreach_reply_monitor.log',
        })

    # Check for recent sends (if no sends today on a weekday)
    if now.weekday() < 5 and now.hour >= 12:
        today_sends = EmailLog.objects.filter(
            status='sent',
            created_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0),
        ).count()
        if today_sends == 0:
            alerts.append({
                'level': 'warn',
                'message': '0 emails sent today (weekday, past noon)',
                'action': 'Check send_sequences logs: docker exec outreach_cron tail -50 /tmp/campaigns_daily.log',
            })

    return {
        'pending_replies': pending_replies,
        'cooling_leads': cooling,
        'upcoming_demos': demos,
        'recent_wins': wins,
        'system_alerts': alerts,
    }


def get_health_status():
    """System health checks as JSON."""
    now = timezone.now()
    checks = {}

    # Last send
    last_send = EmailLog.objects.filter(status='sent').order_by('-created_at').first()
    if last_send:
        age_hours = (now - last_send.created_at).total_seconds() / 3600
        checks['last_send'] = {
            'status': 'ok' if age_hours < 26 else 'warn',
            'value': last_send.created_at.isoformat(),
            'message': f'{age_hours:.0f}h ago',
        }
    else:
        checks['last_send'] = {'status': 'warn', 'value': None, 'message': 'No sends found'}

    # Last reply check
    last_inbound = InboundEmail.objects.order_by('-created_at').first()
    if last_inbound:
        checks['last_reply_check'] = {
            'status': 'ok',
            'value': last_inbound.created_at.isoformat(),
            'message': f'Latest inbound: {last_inbound.created_at.strftime("%H:%M")}',
        }
    else:
        checks['last_reply_check'] = {'status': 'ok', 'value': None, 'message': 'No inbounds yet'}

    # Pending replies
    pending = InboundEmail.objects.filter(needs_reply=True, replied=False).count()
    checks['pending_replies'] = {
        'status': 'ok' if pending == 0 else ('warn' if pending <= 3 else 'critical'),
        'value': pending,
        'message': f'{pending} pending replies',
    }

    # DB connection (if we got here, it works)
    checks['db_connection'] = {
        'status': 'ok',
        'value': None,
        'message': 'Connected',
    }

    # Overall status
    statuses = [c['status'] for c in checks.values()]
    if 'critical' in statuses:
        overall = 'critical'
    elif 'warn' in statuses:
        overall = 'warning'
    else:
        overall = 'healthy'

    alerts = [
        {'check': k, **v}
        for k, v in checks.items()
        if v['status'] != 'ok'
    ]

    return {
        'status': overall,
        'checks': checks,
        'alerts': alerts,
    }


def build_daily_email_context(product_slug=None):
    """Assembles all data needed for the daily KPI email.

    Returns a dict with action-oriented sections:
    DO NOW, WINS, WATCH, NUMBERS, SYSTEM.
    """
    now = timezone.now()
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # --- DO NOW ---
    actions = get_action_items(product_slug)

    # --- WINS (yesterday) ---
    event_qs = ProspectEvent.objects.filter(
        created_at__gte=yesterday_start,
        created_at__lt=yesterday_end,
        to_status__in=['interested', 'demo_scheduled', 'design_partner', 'customer'],
    ).select_related('prospect')
    if product_slug:
        event_qs = event_qs.filter(prospect__campaign__product_ref__slug=product_slug)

    wins = []
    for e in event_qs:
        wins.append({
            'name': e.prospect.decision_maker_name if e.prospect else '',
            'company': e.prospect.business_name if e.prospect else '',
            'status': e.to_status,
        })

    # Auto-replied count + avg response time yesterday
    replied_yesterday = InboundEmail.objects.filter(
        auto_replied=True,
        reply_sent_at__gte=yesterday_start,
        reply_sent_at__lt=yesterday_end,
    )
    if product_slug:
        replied_yesterday = replied_yesterday.filter(campaign__product_ref__slug=product_slug)

    auto_reply_count = replied_yesterday.count()
    response_times = [
        (r.reply_sent_at - r.received_at).total_seconds() / 60
        for r in replied_yesterday
        if r.reply_sent_at and r.received_at
    ]
    avg_response_min = round(sum(response_times) / len(response_times), 0) if response_times else None

    # --- NUMBERS (yesterday) ---
    email_qs = EmailLog.objects.filter(
        status='sent',
        created_at__gte=yesterday_start,
        created_at__lt=yesterday_end,
    )
    if product_slug:
        email_qs = email_qs.filter(campaign__product_ref__slug=product_slug)
    sent_yesterday = email_qs.count()

    # By campaign breakdown
    sent_by_campaign = list(
        email_qs
        .values('campaign__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    replies_yesterday = InboundEmail.objects.filter(
        received_at__gte=yesterday_start,
        received_at__lt=yesterday_end,
    )
    if product_slug:
        replies_yesterday = replies_yesterday.filter(campaign__product_ref__slug=product_slug)
    reply_count = replies_yesterday.count()
    reply_rate = round(reply_count / sent_yesterday * 100, 1) if sent_yesterday else 0.0

    demos_yesterday = ProspectEvent.objects.filter(
        to_status='demo_scheduled',
        created_at__gte=yesterday_start,
        created_at__lt=yesterday_end,
    ).count()

    ai_cost_yesterday = AIUsageLog.objects.filter(
        created_at__gte=yesterday_start,
        created_at__lt=yesterday_end,
    )
    if product_slug:
        ai_cost_yesterday = ai_cost_yesterday.filter(product__slug=product_slug)
    cost = ai_cost_yesterday.aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

    # MTD numbers
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mtd_email_qs = EmailLog.objects.filter(status='sent', created_at__gte=month_start)
    if product_slug:
        mtd_email_qs = mtd_email_qs.filter(campaign__product_ref__slug=product_slug)
    mtd_sent = mtd_email_qs.count()

    mtd_replies = InboundEmail.objects.filter(received_at__gte=month_start)
    if product_slug:
        mtd_replies = mtd_replies.filter(campaign__product_ref__slug=product_slug)
    mtd_reply_count = mtd_replies.count()

    mtd_demos = ProspectEvent.objects.filter(
        to_status='demo_scheduled', created_at__gte=month_start
    ).count()

    mtd_cost = AIUsageLog.objects.filter(created_at__gte=month_start)
    if product_slug:
        mtd_cost = mtd_cost.filter(product__slug=product_slug)
    mtd_cost_total = mtd_cost.aggregate(total=Sum('cost_usd'))['total'] or Decimal('0')

    # --- SYSTEM health ---
    health = get_health_status()

    return {
        'date': now.strftime('%d %b %Y'),
        'do_now': {
            'pending_replies': actions['pending_replies'],
            'upcoming_demos': actions['upcoming_demos'],
        },
        'wins': {
            'new_statuses': wins,
            'auto_reply_count': auto_reply_count,
            'avg_response_min': avg_response_min,
        },
        'watch': {
            'cooling_leads': actions['cooling_leads'],
        },
        'numbers': {
            'sent_yesterday': sent_yesterday,
            'sent_by_campaign': sent_by_campaign,
            'replies': reply_count,
            'reply_rate_pct': reply_rate,
            'demos': demos_yesterday,
            'ai_cost_usd': float(cost),
            'mtd_sent': mtd_sent,
            'mtd_replies': mtd_reply_count,
            'mtd_demos': mtd_demos,
            'mtd_ai_cost_usd': float(mtd_cost_total),
        },
        'system': health,
    }
