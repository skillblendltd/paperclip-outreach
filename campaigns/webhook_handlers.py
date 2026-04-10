"""
TaggIQ -> Paperclip webhook handler.
Receives lifecycle events (trial_started, supplier_connected, etc.)
and creates/updates prospects in lifecycle campaigns.
"""
import hmac
import hashlib
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from campaigns.models import (
    Campaign, Prospect, WebhookEvent,
)

logger = logging.getLogger(__name__)

LIFECYCLE_EVENTS = {
    'trial_started',
    'supplier_connected',
    'first_quote_created',
    'trial_expiring',
    'subscription_started',
    'trial_expired',
}


@csrf_exempt
def taggiq_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    secret = getattr(settings, 'TAGGIQ_WEBHOOK_SECRET', '')
    signature = request.headers.get('X-TaggIQ-Signature', '')

    if secret and signature:
        expected = 'sha256=' + hmac.new(
            secret.encode(), request.body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning('Webhook signature mismatch')
            return JsonResponse({'error': 'Invalid signature'}, status=401)
    elif secret and not signature:
        return JsonResponse({'error': 'Missing signature'}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    delivery_id = request.headers.get('X-TaggIQ-Delivery', '')
    if not delivery_id:
        return JsonResponse({'error': 'Missing X-TaggIQ-Delivery header'}, status=400)

    if WebhookEvent.objects.filter(delivery_id=delivery_id).exists():
        return JsonResponse({'status': 'already_processed'})

    event_type = payload.get('event', 'unknown')
    if event_type not in LIFECYCLE_EVENTS:
        logger.warning(f'Unknown webhook event type: {event_type}')
        return JsonResponse({'error': f'Unknown event: {event_type}'}, status=400)

    event = WebhookEvent.objects.create(
        delivery_id=delivery_id,
        source='taggiq',
        event_type=event_type,
        payload=payload,
    )

    try:
        _handle_event(event)
        event.processed = True
        event.save(update_fields=['processed', 'updated_at'])
    except Exception as e:
        event.error = str(e)
        event.save(update_fields=['error', 'updated_at'])
        logger.error(f'Webhook {event_type} failed: {e}', exc_info=True)

    return JsonResponse({'status': 'ok', 'delivery_id': delivery_id})


def _handle_event(event):
    data = event.payload.get('data', {})
    handler = {
        'trial_started': _handle_trial_started,
        'supplier_connected': _handle_supplier_connected,
        'first_quote_created': _handle_first_quote_created,
        'trial_expiring': _handle_trial_expiring,
        'subscription_started': _handle_subscription_started,
        'trial_expired': _handle_trial_expired,
    }.get(event.event_type)

    if handler:
        handler(data)


def _find_prospect_by_taggiq_user(user_id, email, product_slug='taggiq'):
    """Find existing prospect by taggiq_user_id or email across TaggIQ campaigns."""
    if user_id:
        prospect = Prospect.objects.filter(
            taggiq_user_id=user_id,
            campaign__product_ref__slug=product_slug,
        ).first()
        if prospect:
            return prospect

    if email:
        return Prospect.objects.filter(
            email__iexact=email,
            campaign__product_ref__slug=product_slug,
        ).order_by('-updated_at').first()

    return None


def _get_lifecycle_campaign(campaign_name):
    """Get or warn about missing lifecycle campaign."""
    try:
        return Campaign.objects.get(name=campaign_name)
    except Campaign.DoesNotExist:
        logger.error(f'Lifecycle campaign not found: {campaign_name}')
        return None


def _handle_trial_started(data):
    email = data.get('email', '').lower().strip()
    user_id = data.get('user_id')
    if not email:
        logger.warning('trial_started: no email in payload')
        return

    existing = _find_prospect_by_taggiq_user(user_id, email)
    if existing:
        existing.taggiq_user_id = user_id
        existing.trial_started_at = parse_datetime(data.get('trial_expires_at', '')) and timezone.now()
        trial_expires = data.get('trial_expires_at')
        if trial_expires:
            existing.trial_expires_at = parse_datetime(trial_expires)
        existing.notes = (existing.notes or '') + f'\n[{timezone.now():%Y-%m-%d}] Signed up for TaggIQ trial. Source: {data.get("source", "unknown")}'
        existing.save(update_fields=['taggiq_user_id', 'trial_started_at', 'trial_expires_at', 'notes', 'updated_at'])
        logger.info(f'trial_started: updated existing prospect {existing.email} in {existing.campaign.name}')
        return

    campaign = _get_lifecycle_campaign('TaggIQ Trial Activation')
    if not campaign:
        return

    fname = data.get('first_name', '')
    lname = data.get('last_name', '')
    full_name = f'{fname} {lname}'.strip()

    trial_expires = data.get('trial_expires_at')

    Prospect.objects.create(
        campaign=campaign,
        business_name=data.get('company_name', ''),
        email=email,
        phone=data.get('phone', ''),
        decision_maker_name=full_name,
        region=data.get('country', ''),
        segment='promo_distributor',
        status='new',
        taggiq_user_id=user_id,
        trial_started_at=timezone.now(),
        trial_expires_at=parse_datetime(trial_expires) if trial_expires else None,
        notes=f'TaggIQ trial signup. Source: {data.get("source", "unknown")}',
    )
    logger.info(f'trial_started: created prospect {email} in Trial Activation')


def _handle_supplier_connected(data):
    email = data.get('email', '').lower().strip()
    user_id = data.get('user_id')

    prospect = _find_prospect_by_taggiq_user(user_id, email)
    if not prospect:
        logger.warning(f'supplier_connected: no prospect found for {email}')
        return

    supplier = data.get('supplier_name', 'unknown')
    count = data.get('suppliers_connected', 1)
    prospect.notes = (prospect.notes or '') + f'\n[{timezone.now():%Y-%m-%d}] Connected supplier: {supplier} (total: {count})'

    if prospect.campaign.name == 'TaggIQ Trial Activation' and prospect.emails_sent < 3:
        prospect.send_enabled = False
        prospect.notes += ' - paused activation emails (user is engaged)'

    prospect.save(update_fields=['notes', 'send_enabled', 'updated_at'])
    logger.info(f'supplier_connected: {email} connected {supplier}')


def _handle_first_quote_created(data):
    email = data.get('email', '').lower().strip()
    user_id = data.get('user_id')

    prospect = _find_prospect_by_taggiq_user(user_id, email)
    if not prospect:
        logger.warning(f'first_quote_created: no prospect found for {email}')
        return

    prospect.status = 'engaged'
    prospect.notes = (prospect.notes or '') + f'\n[{timezone.now():%Y-%m-%d}] Created first quote (${data.get("quote_total", 0):.0f} {data.get("currency", "")})'
    prospect.save(update_fields=['status', 'notes', 'updated_at'])

    conversion_campaign = _get_lifecycle_campaign('TaggIQ Trial Conversion')
    if not conversion_campaign:
        return

    if not Prospect.objects.filter(campaign=conversion_campaign, email__iexact=email).exists():
        Prospect.objects.create(
            campaign=conversion_campaign,
            business_name=prospect.business_name,
            email=email,
            phone=prospect.phone,
            decision_maker_name=prospect.decision_maker_name,
            region=prospect.region,
            segment=prospect.segment,
            status='new',
            taggiq_user_id=user_id,
            trial_started_at=prospect.trial_started_at,
            trial_expires_at=prospect.trial_expires_at,
            notes=f'Moved from activation - created first quote',
        )
        logger.info(f'first_quote_created: {email} moved to Trial Conversion')


def _handle_trial_expiring(data):
    email = data.get('email', '').lower().strip()
    user_id = data.get('user_id')

    prospect = _find_prospect_by_taggiq_user(user_id, email)
    if prospect and prospect.status in ('customer', 'demo_scheduled', 'design_partner'):
        logger.info(f'trial_expiring: {email} already {prospect.status}, skipping')
        return

    campaign = _get_lifecycle_campaign('TaggIQ Trial Expiry')
    if not campaign:
        return

    if Prospect.objects.filter(campaign=campaign, email__iexact=email).exists():
        return

    Prospect.objects.create(
        campaign=campaign,
        business_name=prospect.business_name if prospect else '',
        email=email,
        phone=prospect.phone if prospect else '',
        decision_maker_name=prospect.decision_maker_name if prospect else '',
        region=prospect.region if prospect else '',
        segment=prospect.segment if prospect else 'promo_distributor',
        status='new',
        taggiq_user_id=user_id,
        trial_started_at=prospect.trial_started_at if prospect else None,
        trial_expires_at=parse_datetime(data.get('trial_expires_at', '')) if data.get('trial_expires_at') else None,
        notes=f'Trial expiring. Supplier: {data.get("has_connected_supplier")}, Quote: {data.get("has_created_quote")}',
    )
    logger.info(f'trial_expiring: {email} added to Trial Expiry campaign')


def _handle_subscription_started(data):
    email = data.get('email', '').lower().strip()
    user_id = data.get('user_id')

    prospects = Prospect.objects.filter(
        email__iexact=email,
        campaign__product_ref__slug='taggiq',
    )

    plan = data.get('plan', 'unknown')
    mrr = data.get('mrr', 0)
    currency = data.get('currency', 'EUR')

    updated = 0
    for p in prospects:
        p.status = 'customer'
        p.send_enabled = False
        p.notes = (p.notes or '') + f'\n[{timezone.now():%Y-%m-%d}] Subscribed! Plan: {plan}, MRR: {currency} {mrr}'
        p.save(update_fields=['status', 'send_enabled', 'notes', 'updated_at'])
        updated += 1

    logger.info(f'subscription_started: {email} marked as customer across {updated} campaigns')


def _handle_trial_expired(data):
    email = data.get('email', '').lower().strip()
    user_id = data.get('user_id')

    prospect = _find_prospect_by_taggiq_user(user_id, email)
    if prospect and prospect.status == 'customer':
        logger.info(f'trial_expired: {email} is already a customer, skipping')
        return

    campaign = _get_lifecycle_campaign('TaggIQ Win-Back')
    if not campaign:
        return

    if Prospect.objects.filter(campaign=campaign, email__iexact=email).exists():
        return

    Prospect.objects.create(
        campaign=campaign,
        business_name=prospect.business_name if prospect else '',
        email=email,
        phone=prospect.phone if prospect else '',
        decision_maker_name=prospect.decision_maker_name if prospect else '',
        region=prospect.region if prospect else '',
        segment=prospect.segment if prospect else 'promo_distributor',
        status='new',
        taggiq_user_id=user_id,
        trial_started_at=prospect.trial_started_at if prospect else None,
        trial_expires_at=prospect.trial_expires_at if prospect else None,
        notes=f'Trial expired. Had supplier: {data.get("had_connected_supplier")}, Had quote: {data.get("had_created_quote")}',
    )
    logger.info(f'trial_expired: {email} added to Win-Back campaign')
