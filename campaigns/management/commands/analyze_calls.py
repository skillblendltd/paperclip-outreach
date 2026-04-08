"""
Analyze call transcripts and outcomes to improve the calling script.
Runs after each batch of calls. Uses Claude to find patterns.

Usage:
    python manage.py analyze_calls                    # Analyze last 7 days
    python manage.py analyze_calls --days 3           # Analyze last 3 days
    python manage.py analyze_calls --campaign "TaggIQ Ireland"
    python manage.py analyze_calls --apply            # Auto-push improved prompt to Vapi
"""
import json
import logging
import requests
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from campaigns.models import Campaign, CallLog, ScriptInsight

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a sales call analyst. Analyze these cold call transcripts and outcomes for a print/promo shop software company (TaggIQ).

## Current Script
{current_script}

## Call Data ({call_count} calls)
{call_data}

## Your Analysis

Provide a structured analysis in this exact JSON format:
{{
    "answer_rate_pct": <number>,
    "interest_rate_pct": <number>,
    "demo_rate_pct": <number>,
    "top_objections": [
        {{"objection": "...", "frequency": <count>, "current_handling": "good|weak|missing"}},
    ],
    "drop_off_points": [
        {{"moment": "...", "why": "...", "fix": "..."}},
    ],
    "working_hooks": [
        {{"hook": "...", "why_it_works": "..."}},
    ],
    "prospect_language": [
        {{"their_words": "...", "what_it_means": "...", "use_in_script": "..."}},
    ],
    "suggestions": [
        {{"change": "...", "reason": "...", "priority": "high|medium|low"}},
    ],
    "improved_prompt": "<full updated system prompt incorporating learnings>"
}}

Rules:
- Base suggestions on ACTUAL transcript evidence, not theory
- The improved_prompt should be a complete replacement, not a diff
- Keep the same conversational tone — don't make it more corporate
- If something is working, don't change it
- Focus on the top 3 highest-impact changes
- Use the prospect's actual language in the improved script where possible
"""


class Command(BaseCommand):
    help = 'Analyze call transcripts to improve the calling script'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Analyze calls from last N days')
        parser.add_argument('--campaign', type=str, help='Campaign name filter')
        parser.add_argument('--min-calls', type=int, default=5, help='Min calls needed for analysis')
        parser.add_argument('--apply', action='store_true', help='Auto-push improved prompt to Vapi')

    def handle(self, *args, **options):
        days = options['days']
        campaign_name = options.get('campaign')
        min_calls = options['min_calls']
        auto_apply = options.get('apply', False)

        # Smart delta: find calls since last analysis (or fall back to --days)
        last_insight = ScriptInsight.objects.order_by('-created_at').first()
        if last_insight and not options.get('days_explicit'):
            since = last_insight.created_at
            self.stdout.write(f'Delta mode: analyzing calls since last analysis ({since:%Y-%m-%d %H:%M})')
        else:
            since = timezone.now() - timedelta(days=days)
            self.stdout.write(f'Analyzing calls from last {days} days')

        # Get calls with transcripts
        calls = CallLog.objects.filter(
            created_at__gte=since,
            status__in=['answered', 'voicemail'],
        ).exclude(transcript='')

        if campaign_name:
            calls = calls.filter(campaign__name__icontains=campaign_name)

        if calls.count() < min_calls:
            self.stdout.write(f'Only {calls.count()} calls with transcripts (need {min_calls}). Skipping.')
            return

        # Group by campaign
        campaign_ids = calls.values_list('campaign_id', flat=True).distinct()

        for campaign_id in campaign_ids:
            campaign = Campaign.objects.get(id=campaign_id)
            campaign_calls = calls.filter(campaign=campaign)

            self.stdout.write(f'\n=== Analyzing: {campaign.name} ({campaign_calls.count()} calls) ===')
            self._analyze_campaign(campaign, campaign_calls, since, auto_apply)

    def _analyze_campaign(self, campaign, calls, since, auto_apply):
        # Build call data summary
        call_data_lines = []
        total = calls.count()
        answered = calls.filter(status='answered').count()
        interested = calls.filter(disposition__in=['interested', 'demo_booked', 'send_info']).count()
        demos = calls.filter(disposition='demo_booked').count()

        for call in calls[:30]:  # Limit to 30 transcripts to stay in context
            call_data_lines.append(
                f"---\nCall to: {call.prospect.business_name} ({call.prospect.segment})\n"
                f"Status: {call.status} | Disposition: {call.disposition} | Duration: {call.call_duration}s\n"
                f"Transcript:\n{call.transcript[:2000]}\n"
                f"Summary: {call.summary}\n"
                f"Pain signals: {call.pain_signals}\n"
                f"Current tools: {call.current_tools}\n"
            )

        call_data = '\n'.join(call_data_lines)

        # Get current script from config
        try:
            import sys
            sys.path.insert(0, '/Users/pinani/Documents/voysiq/caller')
            from config import _build_system_prompt
            current_script = _build_system_prompt()
        except Exception:
            current_script = "(Current script not available — analyze transcripts only)"

        # Call Claude via Bedrock
        prompt = ANALYSIS_PROMPT.format(
            current_script=current_script[:3000],
            call_count=total,
            call_data=call_data[:15000],
        )

        self.stdout.write('Sending to Claude for analysis...')
        analysis = self._call_claude(prompt)

        if not analysis:
            self.stdout.write(self.style.ERROR('Claude analysis failed'))
            return

        # Parse response
        try:
            # Extract JSON from response
            json_start = analysis.find('{')
            json_end = analysis.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(analysis[json_start:json_end])
            else:
                self.stdout.write(self.style.ERROR('No JSON found in response'))
                self.stdout.write(analysis[:500])
                return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'JSON parse error: {e}'))
            self.stdout.write(analysis[:500])
            return

        # Save insight
        insight = ScriptInsight.objects.create(
            campaign=campaign,
            calls_analyzed=total,
            date_range=f'{since:%Y-%m-%d} to {timezone.now():%Y-%m-%d}',
            answer_rate=result.get('answer_rate_pct', (answered / total * 100) if total else 0),
            interest_rate=result.get('interest_rate_pct', (interested / answered * 100) if answered else 0),
            demo_rate=result.get('demo_rate_pct', (demos / answered * 100) if answered else 0),
            top_objections=json.dumps(result.get('top_objections', []), indent=2),
            drop_off_points=json.dumps(result.get('drop_off_points', []), indent=2),
            working_hooks=json.dumps(result.get('working_hooks', []), indent=2),
            prospect_language=json.dumps(result.get('prospect_language', []), indent=2),
            suggestions=json.dumps(result.get('suggestions', []), indent=2),
            suggested_prompt=result.get('improved_prompt', ''),
        )

        # Print summary
        self.stdout.write(self.style.SUCCESS(f'\n--- Analysis Complete ---'))
        self.stdout.write(f'Calls: {total} | Answered: {answered} ({insight.answer_rate:.0f}%)')
        self.stdout.write(f'Interested: {interested} ({insight.interest_rate:.0f}%) | Demos: {demos} ({insight.demo_rate:.0f}%)')

        self.stdout.write(f'\nTop Objections:')
        for obj in result.get('top_objections', [])[:5]:
            self.stdout.write(f"  - {obj.get('objection')} (x{obj.get('frequency', '?')}) [{obj.get('current_handling', '?')}]")

        self.stdout.write(f'\nDrop-off Points:')
        for dp in result.get('drop_off_points', [])[:3]:
            self.stdout.write(f"  - {dp.get('moment')}: {dp.get('fix')}")

        self.stdout.write(f'\nWorking Hooks:')
        for hook in result.get('working_hooks', [])[:3]:
            self.stdout.write(f"  - {hook.get('hook')}")

        self.stdout.write(f'\nSuggested Changes:')
        for sug in result.get('suggestions', [])[:5]:
            self.stdout.write(f"  [{sug.get('priority', '?')}] {sug.get('change')}")

        # Auto-apply if requested
        if auto_apply and insight.suggested_prompt:
            self.stdout.write(f'\nApplying improved prompt to Vapi...')
            success = self._push_to_vapi(campaign, insight)
            if success:
                insight.prompt_applied = True
                insight.applied_at = timezone.now()
                insight.save(update_fields=['prompt_applied', 'applied_at'])
                self.stdout.write(self.style.SUCCESS('Prompt updated in Vapi!'))
            else:
                self.stdout.write(self.style.ERROR('Failed to update Vapi'))

        self.stdout.write(f'\nInsight saved: {insight.id}')

    def _call_claude(self, prompt):
        """Call Claude via Bedrock proxy or direct."""
        # Try Bedrock proxy first
        proxy_url = 'https://ckvhvigb3lwvycrynjztkea5pm0xstai.lambda-url.us-east-1.on.aws/'
        try:
            response = requests.post(
                f'{proxy_url}chat/completions',
                json={
                    'model': 'claude-sonnet-4-6',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 4000,
                    'temperature': 0.3,
                },
                timeout=120,
            )
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
        except Exception as e:
            logger.warning(f'Bedrock proxy failed: {e}')

        # Fallback: try AWS Bedrock directly via boto3
        try:
            import boto3
            client = boto3.client('bedrock-runtime', region_name='us-east-1')
            response = client.converse(
                modelId='us.anthropic.claude-sonnet-4-6',
                messages=[{'role': 'user', 'content': [{'text': prompt}]}],
                inferenceConfig={'maxTokens': 4000, 'temperature': 0.3},
            )
            return response['output']['message']['content'][0]['text']
        except Exception as e:
            logger.error(f'Bedrock direct failed: {e}')
            return None

    def _push_to_vapi(self, campaign, insight):
        """Push the improved prompt to Vapi assistant."""
        api_key = getattr(settings, 'VAPI_API_KEY', '')
        assistant_id = campaign.vapi_assistant_id or getattr(settings, 'VAPI_ASSISTANT_ID', '')

        if not api_key or not assistant_id:
            return False

        try:
            response = requests.patch(
                f'https://api.vapi.ai/assistant/{assistant_id}',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': {
                        'messages': [{'role': 'system', 'content': insight.suggested_prompt}],
                    },
                },
                timeout=15,
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f'Vapi update failed: {e}')
            return False
