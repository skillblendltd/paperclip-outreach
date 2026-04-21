"""
Outreach API endpoints.
Called by Paperclip AI agents to send personalised outreach emails.
All endpoints are local-only (no auth required).
"""
import json
import logging
from datetime import timedelta

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Q, Count

from campaigns.models import Campaign, Product, Prospect, EmailLog, EmailQueue, Suppression, CallLog, ScriptInsight
from campaigns.email_service import EmailService

logger = logging.getLogger(__name__)


def _queue_post_call_action(call_log, prospect) -> None:
    """Queue the appropriate follow-up email after a Vapi call ends.

    Silent no-op if templates are not yet configured — campaigns without
    post-call templates skip gracefully without raising.
    """
    from campaigns.models import EmailQueue, EmailTemplate
    from datetime import timedelta

    campaign = call_log.campaign
    if not campaign or not campaign.sending_enabled:
        return

    template_name = None
    delay_hours = 0

    if call_log.status == 'voicemail':
        template_name = 'post_call_voicemail'
        delay_hours = 4  # Give them time to check voicemail before email lands

    elif call_log.status == 'answered' and call_log.disposition in ('interested', 'send_info'):
        template_name = 'post_call_demo_link'
        delay_hours = 1  # Strike while the iron is hot

    elif call_log.status == 'answered' and call_log.disposition == 'demo_booked':
        template_name = 'demo_confirmation'
        delay_hours = 0.5

    if not template_name:
        return

    tmpl = EmailTemplate.objects.filter(
        campaign=campaign,
        template_name=template_name,
        is_active=True,
    ).first()
    if not tmpl:
        return  # Template not configured for this campaign yet

    send_after = timezone.now() + timedelta(hours=delay_hours)
    EmailQueue.objects.get_or_create(
        prospect=prospect,
        campaign=campaign,
        template=tmpl,
        status='pending',
        defaults={
            'send_after': send_after,
            'ab_variant': '',
            'triggered_by': 'vapi_webhook',
        },
    )
    logger.info('[vapi_webhook] queued %s for prospect=%s', template_name, prospect.id)


def _append_escalation_note(prospect, reason: str) -> None:
    """Sprint 7 Phase 7.2.6 — stamp an ESCALATION: line on prospect.notes
    and emit a structured warning log. Shared by vapi_webhook and
    send_ai_reply post-send escalation paths.
    """
    timestamp = timezone.now().isoformat()
    line = f'ESCALATION: {reason} - {timestamp}'
    prospect.notes = (prospect.notes + '\n' if prospect.notes else '') + line
    logger.warning(
        'escalation prospect=%s campaign=%s reason=%s',
        prospect.id,
        prospect.campaign_id,
        reason,
    )


def _get_campaign(request, data=None):
    """Resolve campaign from campaign_id in query params or POST body."""
    campaign_id = None
    if data:
        campaign_id = data.get('campaign_id')
    if not campaign_id:
        campaign_id = request.GET.get('campaign_id')
    if not campaign_id:
        return None, JsonResponse({'error': 'campaign_id required'}, status=400)
    try:
        return Campaign.objects.get(id=campaign_id), None
    except Campaign.DoesNotExist:
        try:
            return Campaign.objects.get(name__iexact=campaign_id), None
        except Campaign.DoesNotExist:
            return None, JsonResponse({'error': 'Campaign not found'}, status=404)


def _ab_variant(prospect):
    """Deterministic A/B variant based on prospect ID hash."""
    return 'A' if hash(str(prospect.id)) % 2 == 0 else 'B'


@csrf_exempt
def outreach_send(request):
    """
    POST /api/send/
    Send a single personalised email to a prospect.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    campaign, err = _get_campaign(request, data)
    if err:
        return err

    # 1. Master switch
    if not campaign.sending_enabled:
        return JsonResponse({
            'error': f'Sending DISABLED for campaign "{campaign.name}". Enable in admin.',
            'status': 'blocked',
        }, status=403)

    # 2. Daily limit
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = EmailLog.objects.filter(
        campaign=campaign, created_at__gte=today_start, status='sent'
    ).count()
    if sent_today >= campaign.max_emails_per_day:
        return JsonResponse({
            'error': f'Daily limit reached ({sent_today}/{campaign.max_emails_per_day}).',
            'status': 'rate_limited',
            'sent_today': sent_today,
        }, status=429)

    # 3. Min gap
    last_sent = EmailLog.objects.filter(
        campaign=campaign, status='sent'
    ).order_by('-created_at').first()
    if last_sent:
        gap = timezone.now() - last_sent.created_at
        min_gap = timedelta(minutes=campaign.min_gap_minutes)
        if gap < min_gap:
            wait_seconds = int((min_gap - gap).total_seconds())
            return JsonResponse({
                'error': f'Too soon. Wait {wait_seconds}s (min gap: {campaign.min_gap_minutes}m).',
                'status': 'rate_limited',
                'wait_seconds': wait_seconds,
            }, status=429)

    # 4. Get prospect
    prospect_id = data.get('prospect_id')
    if not prospect_id:
        return JsonResponse({'error': 'prospect_id required'}, status=400)

    try:
        prospect = Prospect.objects.get(id=prospect_id, campaign=campaign)
    except Prospect.DoesNotExist:
        return JsonResponse({'error': 'Prospect not found in this campaign'}, status=404)

    # 5. Prospect sendable?
    if not prospect.send_enabled:
        return JsonResponse({'error': f'Sending disabled for {prospect.business_name}', 'status': 'blocked'}, status=403)

    if prospect.status in ('not_interested', 'opted_out'):
        return JsonResponse({'error': f'Prospect status is {prospect.status}', 'status': 'blocked'}, status=403)

    # Follow-up emails (sequence > 1) only allowed for 'contacted' prospects
    sequence_number_check = data.get('sequence_number', 1)
    if sequence_number_check > 1 and prospect.status != 'contacted':
        return JsonResponse({
            'error': f'Follow-up emails only allowed for contacted prospects (current status: {prospect.status})',
            'status': 'blocked',
        }, status=403)

    if not prospect.email:
        return JsonResponse({'error': f'No email for {prospect.business_name}', 'status': 'blocked'}, status=400)

    # 6. Suppression
    if Suppression.objects.filter(email__iexact=prospect.email).exists():
        return JsonResponse({'error': f'{prospect.email} is suppressed', 'status': 'suppressed'}, status=403)

    sequence_number = data.get('sequence_number', 1)

    # 7. Max per prospect
    prospect_sent = EmailLog.objects.filter(prospect=prospect, status='sent').count()
    if prospect_sent >= campaign.max_emails_per_prospect:
        return JsonResponse({
            'error': f'{prospect.business_name} already received {prospect_sent} emails (max {campaign.max_emails_per_prospect})',
            'status': 'blocked',
        }, status=403)

    # 8. Sequence order
    if campaign.require_sequence_order and sequence_number > 1:
        prev_exists = EmailLog.objects.filter(
            prospect=prospect, sequence_number=sequence_number - 1, status='sent'
        ).exists()
        if not prev_exists:
            return JsonResponse({
                'error': f'Cannot send sequence {sequence_number} - sequence {sequence_number - 1} not sent yet',
                'status': 'blocked',
            }, status=403)

    # 9. Duplicate check
    if EmailLog.objects.filter(prospect=prospect, sequence_number=sequence_number, status='sent').exists():
        return JsonResponse({
            'error': f'Sequence {sequence_number} already sent to {prospect.business_name}',
            'status': 'blocked',
        }, status=403)

    # 10. Render
    subject = data.get('subject', '')
    body_html = data.get('body_html', '')
    template_name = data.get('template_name', '')
    ab_variant = data.get('ab_variant', '') or _ab_variant(prospect)

    # Extract YEAR from notes/pain_signals (format: "Enquiry year: 2021" or "Enquired 2021.")
    year = ''
    for field_text in [prospect.pain_signals, prospect.notes]:
        if 'Enquired ' in field_text:
            for part in field_text.split('.'):
                part = part.strip()
                if part.startswith('Enquired '):
                    val = part.replace('Enquired ', '').strip()
                    if val.isdigit() and len(val) == 4:
                        year = val
                        break
        if not year and 'Enquiry year:' in field_text:
            for part in field_text.split('.'):
                if 'Enquiry year:' in part:
                    val = part.split(':')[-1].strip()
                    if val.isdigit() and len(val) == 4:
                        year = val
                        break
        if year:
            break

    variables = {
        'FNAME': prospect.decision_maker_name.split()[0] if prospect.decision_maker_name else 'there',
        'COMPANY': prospect.business_name,
        'CITY': prospect.city,
        'SEGMENT': prospect.get_segment_display() if prospect.segment else prospect.business_type,
        'YEAR': year or 'a while back',
    }

    rendered_subject = EmailService.render_template(subject, variables)
    rendered_body = EmailService.render_template(body_html, variables)
    rendered_body += campaign.unsubscribe_footer_html

    # 11. Send
    try:
        result = EmailService.send_email(
            to_emails=[prospect.email],
            subject=rendered_subject,
            body_html=rendered_body,
            from_name=campaign.from_name or None,
            from_email=campaign.from_email or None,
            reply_to=campaign.reply_to_email or None,
        )
        status = 'sent'
        error_msg = ''
        ses_id = result.get('message_id', '')
    except Exception as e:
        status = 'failed'
        error_msg = str(e)
        ses_id = ''
        logger.exception(f'Failed to send to {prospect.email}')

    # 12. Log
    log = EmailLog.objects.create(
        campaign=campaign,
        prospect=prospect,
        to_email=prospect.email,
        subject=rendered_subject,
        body_html=rendered_body,
        sequence_number=sequence_number,
        template_name=template_name,
        ab_variant=ab_variant,
        status=status,
        ses_message_id=ses_id,
        error_message=error_msg,
        triggered_by='agent',
    )

    # 13. Update prospect
    if status == 'sent':
        prospect.emails_sent += 1
        prospect.last_emailed_at = timezone.now()
        if prospect.status == 'new':
            prospect.status = 'contacted'
        prospect.save(update_fields=['emails_sent', 'last_emailed_at', 'status', 'updated_at'])

    return JsonResponse({
        'status': status,
        'log_id': str(log.id),
        'prospect': prospect.business_name,
        'to_email': prospect.email,
        'sequence_number': sequence_number,
        'ab_variant': ab_variant,
        'sent_today': sent_today + (1 if status == 'sent' else 0),
        'daily_limit': campaign.max_emails_per_day,
        'error': error_msg or None,
    })


@csrf_exempt
def outreach_prospects(request):
    """GET /api/prospects/?campaign_id=...&tier=A&status=new&has_email=true&limit=50&product=fullypromoted"""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)

    # Support product-level filtering (returns prospects across all campaigns for that product)
    product = request.GET.get('product')
    campaign = None
    valid_products = {code for code, _ in Campaign.PRODUCT_CHOICES}
    if product and not request.GET.get('campaign_id'):
        if product not in valid_products:
            return JsonResponse({
                'error': f'Invalid product "{product}". Valid: {", ".join(sorted(valid_products))}',
            }, status=400)
        qs = Prospect.objects.filter(
            campaign__product_ref__slug=product, send_enabled=True
        ).select_related('campaign')
    else:
        campaign, err = _get_campaign(request)
        if err:
            return err
        product = campaign.product
        qs = Prospect.objects.filter(
            campaign=campaign, send_enabled=True
        ).select_related('campaign')

    tier = request.GET.get('tier')
    if tier:
        qs = qs.filter(tier=tier)

    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)

    segment = request.GET.get('segment')
    if segment:
        qs = qs.filter(segment=segment)

    if request.GET.get('has_email') == 'true':
        qs = qs.exclude(Q(email='') | Q(email__isnull=True))

    suppressed = Suppression.objects.values_list('email', flat=True)
    qs = qs.exclude(email__in=suppressed)

    limit = min(int(request.GET.get('limit', 50)), 1000)
    prospects = qs.order_by('-score')[:limit]

    return JsonResponse({
        'campaign': campaign.name if campaign else f'all_{product}',
        'product': product,
        'count': qs.count(),
        'prospects': [
            {
                'id': str(p.id),
                'business_name': p.business_name,
                'email': p.email,
                'decision_maker_name': p.decision_maker_name,
                'segment': p.segment,
                'tier': p.tier,
                'score': p.score,
                'status': p.status,
                'emails_sent': p.emails_sent,
                'last_emailed_at': p.last_emailed_at.isoformat() if p.last_emailed_at else None,
                'city': p.city,
                'current_tools': p.current_tools,
                'pain_signals': p.pain_signals,
                'notes': p.notes,
                'ab_variant': _ab_variant(p),
                'campaign_name': p.campaign.name,
                'campaign_id': str(p.campaign_id),
            }
            for p in prospects
        ],
    })


@csrf_exempt
def outreach_status(request):
    """GET /api/status/?campaign_id=..."""
    campaign, err = _get_campaign(request)
    if err:
        return err

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = EmailLog.objects.filter(
        campaign=campaign, created_at__gte=today_start, status='sent'
    ).count()

    last_sent = EmailLog.objects.filter(
        campaign=campaign, status='sent'
    ).order_by('-created_at').first()
    last_sent_at = last_sent.created_at.isoformat() if last_sent else None

    ab_stats = {}
    for variant in ['A', 'B']:
        ab_stats[variant] = EmailLog.objects.filter(
            campaign=campaign, ab_variant=variant, status='sent'
        ).count()

    return JsonResponse({
        'campaign': campaign.name,
        'product': campaign.product,
        'sending_enabled': campaign.sending_enabled,
        'max_emails_per_day': campaign.max_emails_per_day,
        'sent_today': sent_today,
        'remaining_today': max(0, campaign.max_emails_per_day - sent_today),
        'last_sent_at': last_sent_at,
        'from_name': campaign.from_name,
        'from_email': campaign.from_email,
        'total_prospects': Prospect.objects.filter(campaign=campaign).count(),
        'prospects_with_email': Prospect.objects.filter(
            campaign=campaign, send_enabled=True
        ).exclude(Q(email='') | Q(email__isnull=True)).count(),
        'suppressed_count': Suppression.objects.count(),
        'ab_stats': ab_stats,
        'safeguards': {
            'master_switch': campaign.sending_enabled,
            'daily_limit': campaign.max_emails_per_day,
            'min_gap_minutes': campaign.min_gap_minutes,
            'max_per_prospect': campaign.max_emails_per_prospect,
            'sequence_order_enforced': campaign.require_sequence_order,
            'duplicate_sequence_blocked': True,
            'suppression_list_active': True,
        },
    })


@csrf_exempt
def outreach_dashboard(request):
    """
    GET /api/dashboard/
    Cross-product overview — shows stats for all products at a glance.
    Optional: ?product=fullypromoted to filter to one product.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)

    product_filter = request.GET.get('product')
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    products = {}
    for code, label in Campaign.PRODUCT_CHOICES:
        if product_filter and code != product_filter:
            continue

        campaigns = Campaign.objects.filter(product_ref__slug=code).annotate(
            _prospect_count=Count('prospects'),
        )
        if not campaigns.exists():
            continue

        product_prospects = Prospect.objects.filter(campaign__product_ref__slug=code)
        total_prospects = product_prospects.count()
        with_email = product_prospects.filter(
            send_enabled=True
        ).exclude(Q(email='') | Q(email__isnull=True)).count()

        product_logs = EmailLog.objects.filter(campaign__product_ref__slug=code, status='sent')
        sent_today = product_logs.filter(created_at__gte=today_start).count()
        total_sent = product_logs.count()

        by_status = {}
        for s_code, s_label in Prospect.STATUS_CHOICES:
            count = product_prospects.filter(status=s_code).count()
            if count > 0:
                by_status[s_code] = count

        products[code] = {
            'label': label,
            'campaigns': [
                {
                    'id': str(c.id),
                    'name': c.name,
                    'sending_enabled': c.sending_enabled,
                    'prospects': c._prospect_count,
                }
                for c in campaigns
            ],
            'total_prospects': total_prospects,
            'prospects_with_email': with_email,
            'sent_today': sent_today,
            'total_sent': total_sent,
            'by_status': by_status,
        }

    return JsonResponse({
        'products': products,
        'suppressed_count': Suppression.objects.count(),
    })


@csrf_exempt
def outreach_queue(request):
    """
    POST /api/queue/
    Queue one or more emails for future sending.

    Body (JSON):
    {
        "campaign_id": "TaggIQ Launch",
        "emails": [
            {
                "prospect_id": "uuid",
                "subject": "Hi {{FNAME}}...",
                "body_html": "<p>...</p>",
                "sequence_number": 1,
                "template_name": "intro_v1",
                "send_after": "2026-03-16T09:00:00"  // optional, defaults to now
            }
        ]
    }

    Or queue a single email:
    {
        "campaign_id": "...",
        "prospect_id": "uuid",
        "subject": "...",
        "body_html": "...",
        "sequence_number": 1,
        "send_after": "2026-03-16T09:00:00"
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    campaign, err = _get_campaign(request, data)
    if err:
        return err

    # Support single or batch
    emails = data.get('emails', [data] if 'prospect_id' in data else [])
    queued = []
    errors = []

    for item in emails:
        prospect_id = item.get('prospect_id')
        if not prospect_id:
            errors.append({'error': 'prospect_id required'})
            continue

        try:
            prospect = Prospect.objects.get(id=prospect_id, campaign=campaign)
        except Prospect.DoesNotExist:
            errors.append({'prospect_id': prospect_id, 'error': 'not found'})
            continue

        seq = item.get('sequence_number', 1)
        send_after_str = item.get('send_after')
        if send_after_str:
            from django.utils.dateparse import parse_datetime
            send_after = parse_datetime(send_after_str)
            if send_after and timezone.is_naive(send_after):
                send_after = timezone.make_aware(send_after)
        else:
            send_after = timezone.now()

        if not send_after:
            send_after = timezone.now()

        # Check if already queued for this sequence
        already = EmailQueue.objects.filter(
            prospect=prospect, sequence_number=seq, status='pending'
        ).exists()
        if already:
            errors.append({
                'prospect_id': prospect_id,
                'error': f'seq {seq} already queued',
            })
            continue

        variant = item.get('ab_variant', '') or _ab_variant(prospect)

        q = EmailQueue.objects.create(
            campaign=campaign,
            prospect=prospect,
            subject=item.get('subject', ''),
            body_html=item.get('body_html', ''),
            sequence_number=seq,
            template_name=item.get('template_name', ''),
            ab_variant=variant,
            send_after=send_after,
        )
        queued.append({
            'queue_id': str(q.id),
            'prospect': prospect.business_name,
            'email': prospect.email,
            'sequence_number': seq,
            'send_after': q.send_after.isoformat(),
        })

    return JsonResponse({
        'status': 'ok',
        'campaign': campaign.name,
        'queued': len(queued),
        'errors': len(errors),
        'items': queued,
        'error_details': errors if errors else None,
    })


@csrf_exempt
def outreach_queue_status(request):
    """
    GET /api/queue/status/?campaign_id=...
    Show queue stats.
    """
    campaign, err = _get_campaign(request)
    if err:
        return err

    pending = EmailQueue.objects.filter(campaign=campaign, status='pending')
    due = pending.filter(send_after__lte=timezone.now()).count()

    return JsonResponse({
        'campaign': campaign.name,
        'pending': pending.count(),
        'due_now': due,
        'sent': EmailQueue.objects.filter(campaign=campaign, status='sent').count(),
        'failed': EmailQueue.objects.filter(campaign=campaign, status='failed').count(),
        'cancelled': EmailQueue.objects.filter(campaign=campaign, status='cancelled').count(),
    })


@csrf_exempt
def outreach_import_prospects(request):
    """POST /api/import/ - Import prospects as JSON array."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    campaign, err = _get_campaign(request, data)
    if err:
        return err

    prospects_data = data.get('prospects', [])
    created = 0
    updated = 0
    skipped = 0

    for p in prospects_data:
        email = (p.get('email') or '').strip()
        name = (p.get('business_name') or '').strip()
        if not name:
            skipped += 1
            continue

        existing = None
        if email:
            existing = Prospect.objects.filter(campaign=campaign, email__iexact=email).first()
        if not existing:
            existing = Prospect.objects.filter(campaign=campaign, business_name__iexact=name).first()

        if existing:
            for field in ['email', 'phone', 'city', 'region', 'decision_maker_name',
                          'decision_maker_title', 'segment', 'tier', 'score',
                          'current_tools', 'pain_signals', 'notes', 'website',
                          'business_type']:
                val = p.get(field, '').strip() if isinstance(p.get(field, ''), str) else p.get(field)
                if val and (not getattr(existing, field, None) or field in ('score', 'tier')):
                    setattr(existing, field, val)
            existing.save()
            updated += 1
        else:
            Prospect.objects.create(
                campaign=campaign,
                business_name=name,
                email=email,
                website=p.get('website') or '',
                phone=p.get('phone') or '',
                city=p.get('city') or '',
                region=p.get('region') or '',
                decision_maker_name=p.get('decision_maker_name') or '',
                decision_maker_title=p.get('decision_maker_title') or '',
                business_type=p.get('business_type') or '',
                segment=p.get('segment') or '',
                tier=p.get('tier') or 'C',
                score=int(p.get('score') or 0),
                current_tools=p.get('current_tools') or '',
                pain_signals=p.get('pain_signals') or '',
                notes=p.get('notes') or '',
            )
            created += 1

    return JsonResponse({
        'status': 'ok',
        'campaign': campaign.name,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'total': Prospect.objects.filter(campaign=campaign).count(),
    })


@csrf_exempt
def vapi_webhook(request):
    """
    Receive Vapi end-of-call webhooks.
    Updates CallLog with outcome, transcript, recording, and updates Prospect status.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    message_type = data.get('message', {}).get('type', '') if 'message' in data else data.get('type', '')

    # Handle end-of-call report
    if message_type == 'end-of-call-report':
        message = data.get('message', data)
        call_data = message.get('call', {})
        vapi_call_id = call_data.get('id', '')

        if not vapi_call_id:
            return JsonResponse({'error': 'No call ID'}, status=400)

        try:
            call_log = CallLog.objects.get(vapi_call_id=vapi_call_id)
        except CallLog.DoesNotExist:
            logger.warning(f'CallLog not found for vapi_call_id: {vapi_call_id}')
            return JsonResponse({'status': 'ignored', 'reason': 'call not found'})

        # Update call log
        call_log.transcript = message.get('transcript', '')
        call_log.recording_url = message.get('recordingUrl', '')
        call_log.summary = message.get('summary', '')

        # Duration
        started = call_data.get('startedAt', '')
        ended = call_data.get('endedAt', '')
        if started and ended:
            from datetime import datetime
            try:
                start_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(ended.replace('Z', '+00:00'))
                call_log.call_duration = int((end_dt - start_dt).total_seconds())
            except (ValueError, TypeError):
                pass

        # Determine status from call end reason
        end_reason = call_data.get('endedReason', '')
        if end_reason in ('customer-did-not-answer', 'customer-busy'):
            call_log.status = 'no_answer'
        elif end_reason == 'voicemail':
            call_log.status = 'voicemail'
        elif call_log.call_duration > 0:
            call_log.status = 'answered'

        # Extract structured data from analysis
        analysis = message.get('analysis', {})
        structured = analysis.get('structuredData', {})

        if structured.get('appointmentBooked'):
            call_log.disposition = 'demo_booked'

        call_summary = structured.get('callSummary', '') or analysis.get('summary', '')
        if call_summary:
            call_log.summary = call_summary

        call_log.save()

        # Update prospect fields that don't involve status
        prospect = call_log.prospect
        if call_log.email_captured:
            if not prospect.email:
                prospect.email = call_log.email_captured
        if call_log.current_tools:
            prospect.current_tools = call_log.current_tools
        if call_log.pain_signals:
            prospect.pain_signals = call_log.pain_signals
        prospect.save(update_fields=[
            'email', 'current_tools', 'pain_signals', 'updated_at'
        ] if any([call_log.email_captured, call_log.current_tools, call_log.pain_signals])
          else ['updated_at'])

        # Status transitions go through lifecycle gateway
        from campaigns.services import lifecycle
        disposition_to_status = {
            'demo_booked':    'demo_scheduled',
            'interested':     'interested',
            'not_interested': 'not_interested',
            'do_not_call':    'opted_out',
        }
        target_status = disposition_to_status.get(call_log.disposition)
        if target_status:
            try:
                lifecycle.transition(
                    prospect, target_status,
                    reason=f'call:disposition={call_log.disposition}',
                    triggered_by='vapi_webhook',
                )
            except ValueError as exc:
                logger.warning('[vapi_webhook] lifecycle skip for %s: %s', prospect.id, exc)

        # Queue post-call follow-up emails
        _queue_post_call_action(call_log, prospect)

        # Sprint 7 Phase 7.2.5 — brain state machine on flag=True campaigns.
        # Runs after lifecycle transition. rules_engine.apply_call_outcome returns an
        # OutcomeEffect; we apply new_status if it differs from current, log escalations.
        if getattr(call_log.campaign, 'use_context_assembler', False):
            try:
                from campaigns.services.brain import load_brain, BrainNotFound
                from campaigns.services import rules_engine, next_action
                brain = load_brain(prospect)
                effect = rules_engine.apply_call_outcome(brain, prospect, call_log)
                if effect.new_status and effect.new_status != prospect.status:
                    try:
                        lifecycle.transition(
                            prospect, effect.new_status,
                            reason=f'brain:call_outcome={effect.reason}',
                            triggered_by='vapi_webhook:brain',
                        )
                    except ValueError as exc:
                        logger.warning('[sprint7 webhook] brain lifecycle skip: %s', exc)
                if effect.handoff == 'escalation':
                    _append_escalation_note(prospect, effect.reason or 'call_outcome')
                    prospect.save(update_fields=['notes', 'updated_at'])
                # Log the next_action decision (observability only — cron executes it).
                try:
                    na = next_action.decide_next_action(prospect)
                    logger.info(
                        '[sprint7 webhook] prospect=%s next_action channel=%s reason=%s brain_v=%s',
                        prospect.id, na.channel, na.reason, na.brain_version,
                    )
                except Exception as exc:
                    logger.warning(f'[sprint7 webhook] next_action failed for {prospect.id}: {exc}')
            except BrainNotFound as exc:
                logger.warning(f'[sprint7 webhook] no brain for prospect {prospect.id}: {exc}')
            except Exception as exc:
                logger.exception(f'[sprint7 webhook] brain state machine error: {exc}')

        logger.info(f'[VAPI WEBHOOK] Updated call {vapi_call_id}: status={call_log.status}, disposition={call_log.disposition}')
        return JsonResponse({'status': 'ok', 'call_id': vapi_call_id})

    # Handle function calls (capture_email, end_call, etc.)
    elif message_type == 'function-call':
        message = data.get('message', data)
        func_call = message.get('functionCall', {})
        func_name = func_call.get('name', '')
        params = func_call.get('parameters', {})

        call_data = message.get('call', {})
        vapi_call_id = call_data.get('id', '')

        if not vapi_call_id:
            return JsonResponse({'status': 'ignored'})

        try:
            call_log = CallLog.objects.get(vapi_call_id=vapi_call_id)
        except CallLog.DoesNotExist:
            return JsonResponse({'status': 'ignored'})

        if func_name == 'capture_email':
            call_log.email_captured = params.get('email', '')
            call_log.save(update_fields=['email_captured'])

        elif func_name == 'end_call':
            disposition = params.get('outcome', 'pending')
            call_log.disposition = disposition
            call_log.current_tools = params.get('current_tools', '')
            call_log.pain_signals = params.get('pain_signals', '')
            if not call_log.summary:
                call_log.summary = params.get('summary', '')
            call_log.save()

        elif func_name == 'schedule_callback':
            call_log.callback_time = params.get('callback_time', '')
            call_log.disposition = 'callback_requested'
            call_log.save(update_fields=['callback_time', 'disposition'])

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'ignored'})


@csrf_exempt
def outreach_calls(request):
    """
    GET /api/calls/?campaign_id=...&status=answered&disposition=interested&limit=50&product=fullypromoted
    List call logs with filtering.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)

    product = request.GET.get('product')
    campaign = None
    if product and not request.GET.get('campaign_id'):
        qs = CallLog.objects.filter(
            campaign__product_ref__slug=product
        ).select_related('campaign', 'prospect')
    else:
        campaign, err = _get_campaign(request)
        if err:
            return err
        product = campaign.product
        qs = CallLog.objects.filter(
            campaign=campaign
        ).select_related('campaign', 'prospect')

    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)

    disposition = request.GET.get('disposition')
    if disposition:
        qs = qs.filter(disposition=disposition)

    has_transcript = request.GET.get('has_transcript')
    if has_transcript == 'true':
        qs = qs.exclude(Q(transcript='') | Q(transcript__isnull=True))

    limit = min(int(request.GET.get('limit', 50)), 500)
    calls = qs.order_by('-created_at')[:limit]

    return JsonResponse({
        'campaign': campaign.name if campaign else f'all_{product}',
        'product': product,
        'count': qs.count(),
        'calls': [
            {
                'id': str(c.id),
                'prospect_id': str(c.prospect_id),
                'prospect_name': c.prospect.business_name,
                'phone_number': c.phone_number,
                'status': c.status,
                'disposition': c.disposition,
                'call_duration': c.call_duration,
                'vapi_call_id': c.vapi_call_id,
                'recording_url': c.recording_url,
                'transcript': c.transcript[:500] if c.transcript else '',
                'summary': c.summary,
                'email_captured': c.email_captured,
                'callback_time': c.callback_time,
                'current_tools': c.current_tools,
                'pain_signals': c.pain_signals,
                'campaign_name': c.campaign.name,
                'campaign_id': str(c.campaign_id),
                'created_at': c.created_at.isoformat(),
            }
            for c in calls
        ],
    })


@csrf_exempt
def outreach_calls_stats(request):
    """
    GET /api/calls/stats/?campaign_id=...&product=fullypromoted
    Call statistics and performance metrics.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)

    product = request.GET.get('product')
    campaign = None
    if product and not request.GET.get('campaign_id'):
        qs = CallLog.objects.filter(campaign__product_ref__slug=product)
    else:
        campaign, err = _get_campaign(request)
        if err:
            return err
        product = campaign.product
        qs = CallLog.objects.filter(campaign=campaign)

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    total = qs.count()
    today = qs.filter(created_at__gte=today_start).count()

    by_status = {}
    for code, label in CallLog.STATUS_CHOICES:
        count = qs.filter(status=code).count()
        if count > 0:
            by_status[code] = count

    by_disposition = {}
    for code, label in CallLog.DISPOSITION_CHOICES:
        count = qs.filter(disposition=code).count()
        if count > 0:
            by_disposition[code] = count

    answered = qs.filter(status='answered')
    answered_count = answered.count()

    from django.db.models import Avg, Sum
    avg_duration = answered.aggregate(avg=Avg('call_duration'))['avg'] or 0
    total_duration = answered.aggregate(total=Sum('call_duration'))['total'] or 0

    answer_rate = round((answered_count / total * 100), 1) if total > 0 else 0
    interested_count = qs.filter(disposition__in=['interested', 'demo_booked', 'send_info']).count()
    interest_rate = round((interested_count / answered_count * 100), 1) if answered_count > 0 else 0
    demo_count = qs.filter(disposition='demo_booked').count()
    demo_rate = round((demo_count / answered_count * 100), 1) if answered_count > 0 else 0

    return JsonResponse({
        'campaign': campaign.name if campaign else f'all_{product}',
        'product': product,
        'total_calls': total,
        'calls_today': today,
        'by_status': by_status,
        'by_disposition': by_disposition,
        'answer_rate': answer_rate,
        'interest_rate': interest_rate,
        'demo_rate': demo_rate,
        'avg_call_duration': round(avg_duration, 1),
        'total_call_minutes': round(total_duration / 60, 1),
    })


@csrf_exempt
def outreach_script_insights(request):
    """
    GET /api/script-insights/?campaign_id=...&product=taggiq&limit=10
    List AI-generated script insights from call transcript analysis.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)

    product = request.GET.get('product')
    campaign = None
    if product and not request.GET.get('campaign_id'):
        qs = ScriptInsight.objects.filter(
            campaign__product_ref__slug=product
        ).select_related('campaign')
    else:
        campaign, err = _get_campaign(request)
        if err:
            return err
        product = campaign.product
        qs = ScriptInsight.objects.filter(
            campaign=campaign
        ).select_related('campaign')

    limit = min(int(request.GET.get('limit', 10)), 50)
    insights = qs.order_by('-created_at')[:limit]

    return JsonResponse({
        'campaign': campaign.name if campaign else f'all_{product}',
        'product': product,
        'count': qs.count(),
        'insights': [
            {
                'id': str(i.id),
                'campaign_name': i.campaign.name,
                'campaign_id': str(i.campaign_id),
                'calls_analyzed': i.calls_analyzed,
                'date_range': i.date_range,
                'answer_rate': i.answer_rate,
                'interest_rate': i.interest_rate,
                'demo_rate': i.demo_rate,
                'top_objections': i.top_objections,
                'drop_off_points': i.drop_off_points,
                'working_hooks': i.working_hooks,
                'prospect_language': i.prospect_language,
                'suggestions': i.suggestions,
                'prompt_applied': i.prompt_applied,
                'applied_at': i.applied_at.isoformat() if i.applied_at else None,
                'created_at': i.created_at.isoformat(),
            }
            for i in insights
        ],
    })
