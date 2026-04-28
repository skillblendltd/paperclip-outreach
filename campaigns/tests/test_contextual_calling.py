"""Tests for the warm-trigger contextual calling pipeline (Sprint 9).

Covers:
  1. CallTask model: idempotency under repeated warm transitions
  2. call_trigger.on_warm_transition: produces a CallTask only for warm states
     and respects eligibility gates (no phone, send_disabled, etc.)
  3. lifecycle.transition: post-hook fires call_trigger for warm transitions
  4. process_call_queue: dispatches via the provider boundary using a mock
     provider — proves the abstraction works without Vapi
  5. CallProvider parse_webhook: a Vapi end-of-call payload normalizes to a
     CallEvent with the correct disposition / status / correlation_id
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from campaigns.call_provider.base import (
    CallEvent, CallPrompt, CallResult, place, parse_webhook, register, _REGISTRY,
)
from campaigns.models import (
    CallLog, CallTask, Campaign, Organization, Product, Prospect, ProspectEvent,
)
from campaigns.services import call_trigger, lifecycle


class _MockProvider:
    """Provider that records every call and returns scripted results."""

    slug = 'mock'

    def __init__(self):
        self.calls = []
        self.next_result = CallResult(success=True, provider_call_id='mock-call-1')

    def place_call(self, prospect, prompt: CallPrompt) -> CallResult:
        self.calls.append({'prospect': prospect, 'prompt': prompt})
        return self.next_result

    def parse_webhook(self, raw: dict):
        return None


class CallTaskIdempotencyTests(TestCase):
    """Verify the partial unique index + update_or_create pattern."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='T', slug='t-call-idem')
        cls.product = Product.objects.create(
            organization=cls.org, name='Prod', slug='prod-call-idem',
        )
        cls.campaign = Campaign.objects.create(
            name='Call Idem',
            product='other',
            product_ref=cls.product,
            from_email='x@example.test',
            from_name='X',
            calling_enabled=True,
        )

    def _mk_prospect(self, status='contacted'):
        return Prospect.objects.create(
            campaign=self.campaign,
            business_name='Biz',
            email='biz@example.test',
            phone='+15555550100',
            status=status,
            send_enabled=True,
        )

    def test_one_pending_calltask_per_prospect_via_update_or_create(self):
        p = self._mk_prospect()
        # Two consecutive transitions to interested (e.g. two replies in a row).
        # Bypass the lifecycle gateway here so we exercise the trigger directly.
        ev1 = ProspectEvent.objects.create(
            prospect=p, from_status='contacted', to_status='interested',
            reason='reply:1', triggered_by='test',
        )
        p.status = 'interested'
        p.save(update_fields=['status', 'updated_at'])
        task1 = call_trigger.on_warm_transition(p, ev1)
        self.assertIsNotNone(task1)

        ev2 = ProspectEvent.objects.create(
            prospect=p, from_status='interested', to_status='interested',
            reason='reply:2', triggered_by='test',
        )
        task2 = call_trigger.on_warm_transition(p, ev2)
        self.assertEqual(task1.id, task2.id,
            'Second warm transition must update the same pending CallTask, not duplicate')

        self.assertEqual(
            CallTask.objects.filter(prospect=p, status='pending').count(), 1,
        )


class WarmTriggerEligibilityTests(TestCase):
    """call_trigger.on_warm_transition must decline for non-warm or
    ineligible prospects."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='T', slug='t-warm-elig')
        cls.product = Product.objects.create(
            organization=cls.org, name='P', slug='p-warm-elig',
        )
        cls.campaign = Campaign.objects.create(
            name='Warm Elig',
            product='other',
            product_ref=cls.product,
            from_email='x@example.test',
            from_name='X',
            calling_enabled=True,
        )

    def _mk_prospect(self, **overrides):
        defaults = dict(
            campaign=self.campaign,
            business_name='Biz',
            email='biz@example.test',
            phone='+15555550101',
            status='interested',
            send_enabled=True,
        )
        defaults.update(overrides)
        return Prospect.objects.create(**defaults)

    def test_skip_when_prospect_has_no_phone(self):
        p = self._mk_prospect(phone='')
        task = call_trigger.on_warm_transition(p, None)
        self.assertIsNone(task)
        self.assertFalse(CallTask.objects.filter(prospect=p).exists())

    def test_skip_when_send_disabled(self):
        p = self._mk_prospect(send_enabled=False)
        task = call_trigger.on_warm_transition(p, None)
        self.assertIsNone(task)

    def test_skip_when_status_not_warm(self):
        p = self._mk_prospect(status='contacted')
        task = call_trigger.on_warm_transition(p, None)
        self.assertIsNone(task)

    def test_skip_when_campaign_calling_disabled(self):
        p = self._mk_prospect()
        Campaign.objects.filter(pk=self.campaign.pk).update(calling_enabled=False)
        p.refresh_from_db()
        task = call_trigger.on_warm_transition(p, None)
        self.assertIsNone(task)

    def test_creates_task_when_eligible_and_warm(self):
        p = self._mk_prospect()
        ev = ProspectEvent.objects.create(
            prospect=p, from_status='contacted', to_status='interested',
            reason='reply:interested', triggered_by='test',
        )
        task = call_trigger.on_warm_transition(p, ev)
        self.assertIsNotNone(task)
        self.assertEqual(task.status, 'pending')
        self.assertEqual(task.prospect, p)
        self.assertIn('warm:', task.reason)


class LifecyclePostHookTests(TestCase):
    """lifecycle.transition() must fire the call_trigger post-hook on warm
    transitions and not interfere with non-warm transitions."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='T', slug='t-life-hook')
        cls.product = Product.objects.create(
            organization=cls.org, name='P', slug='p-life-hook',
        )
        cls.campaign = Campaign.objects.create(
            name='Life Hook',
            product='other',
            product_ref=cls.product,
            from_email='x@example.test',
            from_name='X',
            calling_enabled=True,
        )

    def _mk_prospect(self, status='contacted'):
        return Prospect.objects.create(
            campaign=self.campaign,
            business_name='Biz',
            email='biz@example.test',
            phone='+15555550102',
            status=status,
            send_enabled=True,
        )

    def test_transition_to_interested_creates_calltask(self):
        p = self._mk_prospect(status='contacted')
        lifecycle.transition(p, 'interested',
                             reason='reply:interested', triggered_by='test')
        self.assertEqual(
            CallTask.objects.filter(prospect=p, status='pending').count(), 1,
        )

    def test_transition_to_not_interested_does_not_create_calltask(self):
        p = self._mk_prospect(status='contacted')
        lifecycle.transition(p, 'not_interested',
                             reason='reply:not_interested', triggered_by='test')
        self.assertEqual(CallTask.objects.filter(prospect=p).count(), 0)


class ProcessCallQueueDispatchTests(TestCase):
    """The dispatch path uses the provider-agnostic boundary. A mock provider
    proves the abstraction is real."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='T', slug='t-disp')
        cls.product = Product.objects.create(
            organization=cls.org, name='P', slug='p-disp',
        )
        cls.campaign = Campaign.objects.create(
            name='Dispatch',
            product='other',
            product_ref=cls.product,
            from_email='x@example.test',
            from_name='X',
            calling_enabled=True,
            send_window_timezone='Europe/Dublin',
        )

    def _mk_prospect_and_task(self):
        p = Prospect.objects.create(
            campaign=self.campaign,
            business_name='Biz',
            email='biz@example.test',
            phone='+15555550103',
            status='interested',
            send_enabled=True,
        )
        task = CallTask.objects.create(
            prospect=p,
            scheduled_for=timezone.now() - timedelta(minutes=1),
            reason='warm:reply:interested',
        )
        return p, task

    def test_dispatch_calls_mock_provider_and_marks_task_dispatched(self):
        p, task = self._mk_prospect_and_task()

        mock = _MockProvider()
        register(mock)
        try:
            from campaigns.management.commands.process_call_queue import Command
            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.stderr = MagicMock()
            cmd.style = MagicMock()
            cmd.style.WARNING = lambda s: s
            cmd.style.SUCCESS = lambda s: s
            cmd.style.ERROR = lambda s: s
            ok, err = cmd._dispatch(task, provider_slug='mock')
        finally:
            _REGISTRY.pop('mock', None)

        self.assertTrue(ok, msg=f'expected dispatch success, got err={err!r}')
        task.refresh_from_db()
        self.assertEqual(task.status, 'dispatched')
        self.assertEqual(task.provider_call_id, 'mock-call-1')
        self.assertEqual(len(mock.calls), 1)
        prompt = mock.calls[0]['prompt']
        self.assertIsInstance(prompt, CallPrompt)
        # No `{{vars}}` in the rendered first_message — Paperclip rule.
        self.assertNotIn('{{', prompt.first_message)
        self.assertNotIn('{{', prompt.system_prompt)
        # CallLog row written with the provider_call_id (named vapi_call_id).
        self.assertEqual(
            CallLog.objects.filter(prospect=p, vapi_call_id='mock-call-1').count(), 1,
        )

    def test_dispatch_skips_when_prospect_phone_cleared(self):
        p, task = self._mk_prospect_and_task()
        Prospect.objects.filter(pk=p.pk).update(phone='')
        p.refresh_from_db()

        mock = _MockProvider()
        register(mock)
        try:
            from campaigns.management.commands.process_call_queue import Command
            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.stderr = MagicMock()
            cmd.style = MagicMock()
            cmd.style.WARNING = lambda s: s
            cmd.style.SUCCESS = lambda s: s
            cmd.style.ERROR = lambda s: s
            reason = cmd._late_check_skip_reason(p)
        finally:
            _REGISTRY.pop('mock', None)
        self.assertEqual(reason, 'prospect_phone_cleared')


class VapiAdapterParseWebhookTests(TestCase):
    """Verify the Vapi adapter normalizes an end-of-call payload correctly."""

    def test_parse_end_of_call_extracts_disposition_and_correlation_id(self):
        from campaigns.call_provider import vapi as vapi_adapter
        provider = vapi_adapter.VapiProvider()
        raw = {
            'message': {
                'type': 'end-of-call-report',
                'transcript': 'Operator: ... Customer: yes please.',
                'recordingUrl': 'https://example.test/rec.wav',
                'analysis': {
                    'structuredData': {'appointmentBooked': True},
                    'summary': 'Booked demo for Tuesday',
                },
                'call': {
                    'id': 'vapi-call-xyz',
                    'startedAt': '2026-04-28T10:00:00.000Z',
                    'endedAt':   '2026-04-28T10:02:30.000Z',
                    'endedReason': 'customer-ended',
                    'assistantOverrides': {
                        'metadata': {'correlation_id': 'task-uuid-123'},
                    },
                },
            },
        }
        event = provider.parse_webhook(raw)
        self.assertIsNotNone(event)
        self.assertEqual(event.provider_call_id, 'vapi-call-xyz')
        self.assertEqual(event.correlation_id, 'task-uuid-123')
        self.assertEqual(event.disposition, 'demo_booked')
        self.assertEqual(event.duration_seconds, 150)
        self.assertEqual(event.event_type, 'answered')
        self.assertIn('Booked demo', event.summary)

    def test_parse_function_call_returns_none(self):
        from campaigns.call_provider import vapi as vapi_adapter
        provider = vapi_adapter.VapiProvider()
        raw = {'message': {'type': 'function-call'}}
        event = provider.parse_webhook(raw)
        self.assertIsNone(event)

    def test_parse_no_answer(self):
        from campaigns.call_provider import vapi as vapi_adapter
        provider = vapi_adapter.VapiProvider()
        raw = {
            'message': {
                'type': 'end-of-call-report',
                'call': {
                    'id': 'vapi-noanswer',
                    'endedReason': 'customer-did-not-answer',
                    'startedAt': '2026-04-28T10:00:00.000Z',
                    'endedAt':   '2026-04-28T10:00:30.000Z',
                },
            },
        }
        event = provider.parse_webhook(raw)
        self.assertEqual(event.event_type, 'no_answer')
