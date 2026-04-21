"""
Call Service for Paperclip Outreach
Places outbound calls via Vapi.ai API
"""
import logging
import requests
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)

VAPI_API_URL = 'https://api.vapi.ai'


class CallService:
    @staticmethod
    def place_call(
        phone_number: str,
        assistant_id: str,
        phone_number_id: str,
        prospect_name: str = '',
        company_name: str = '',
        segment: str = '',
        first_message: str = '',
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Place an outbound call via Vapi.
        Returns dict with 'success', 'call_id', 'error'.

        first_message: when provided, overrides the CallScript DB lookup and
        goes directly into Vapi's assistantOverrides.firstMessage. This is how
        dynamic Claude-generated openers reach the voice agent.
        """
        api_key = getattr(settings, 'VAPI_API_KEY', '')
        if not api_key:
            logger.error('VAPI_API_KEY not configured')
            return {'success': False, 'call_id': '', 'error': 'VAPI_API_KEY not configured'}

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        # Use provided first_message if given, otherwise look up from CallScript DB
        resolved_first_message = first_message or CallService._get_first_message(
            assistant_id, segment, prospect_name
        )

        payload = {
            'assistantId': assistant_id,
            'phoneNumberId': phone_number_id,
            'customer': {
                'number': phone_number,
                'name': prospect_name or 'there',
            },
            'assistantOverrides': {
                'firstMessage': resolved_first_message,
                'metadata': {
                    'prospect_name': prospect_name,
                    'company_name': company_name,
                    'segment': segment,
                    **(metadata or {}),
                },
            },
        }

        try:
            logger.info(f'[CALL SERVICE] Placing call to {phone_number} ({company_name})')
            response = requests.post(
                f'{VAPI_API_URL}/call/phone',
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code in (200, 201):
                data = response.json()
                call_id = data.get('id', '')
                logger.info(f'[CALL SERVICE] Call placed successfully: {call_id}')
                return {'success': True, 'call_id': call_id, 'error': ''}
            else:
                error = response.text[:500]
                logger.error(f'[CALL SERVICE] Failed ({response.status_code}): {error}')
                return {'success': False, 'call_id': '', 'error': error}

        except requests.RequestException as e:
            logger.error(f'[CALL SERVICE] Request error: {e}')
            return {'success': False, 'call_id': '', 'error': str(e)}

    @staticmethod
    def _get_first_message(assistant_id: str, segment: str, prospect_name: str = '') -> str:
        """Look up first message from CallScript model, fallback to hardcoded defaults.

        Renders {{FNAME}} and {{NAME}} template vars before returning so the
        voice agent always receives a ready-to-speak string.
        """
        raw = None
        try:
            from campaigns.models import CallScript, Campaign
            # Find campaign by vapi_assistant_id
            campaign = Campaign.objects.filter(vapi_assistant_id=assistant_id).first()
            if campaign:
                script = CallScript.objects.filter(
                    campaign=campaign, segment=segment, is_active=True
                ).first()
                if script and script.first_message:
                    raw = script.first_message
                else:
                    # Try default (empty segment)
                    script = CallScript.objects.filter(
                        campaign=campaign, segment='', is_active=True
                    ).first()
                    if script and script.first_message:
                        raw = script.first_message
        except Exception:
            pass

        if raw is None:
            # Fallback to hardcoded defaults
            defaults = {
                'signs': "Hi there, I'm calling from TaggIQ. We work with sign and print shops. Have you got 30 seconds?",
                'apparel_embroidery': "Hi there, I'm calling from TaggIQ. We work with embroidery and apparel shops. Have you got 30 seconds?",
                'print_shop': "Hi there, I'm calling from TaggIQ. We work with print and promo shops. Have you got 30 seconds?",
                'promo_distributor': "Hi there, I'm calling from TaggIQ. We work with promotional product businesses. Have you got 30 seconds?",
            }
            raw = defaults.get(segment, "Hi there, I'm calling from TaggIQ. We work with print and promo shops. Have you got 30 seconds?")

        # Render template variables
        name = prospect_name or 'there'
        raw = raw.replace('{{FNAME}}', name).replace('{{NAME}}', name)
        return raw

    @staticmethod
    def get_call_status(call_id: str) -> Dict[str, Any]:
        """Fetch call status from Vapi."""
        api_key = getattr(settings, 'VAPI_API_KEY', '')
        if not api_key:
            return {'error': 'VAPI_API_KEY not configured'}

        try:
            response = requests.get(
                f'{VAPI_API_URL}/call/{call_id}',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                timeout=15,
            )
            if response.status_code == 200:
                return response.json()
            return {'error': f'HTTP {response.status_code}: {response.text[:200]}'}
        except requests.RequestException as e:
            return {'error': str(e)}
