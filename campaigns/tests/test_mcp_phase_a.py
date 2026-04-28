"""Phase A tests for the MCP integration boundary.

Covers:
  1. Models — connection scoping, unique constraints
  2. Registry — default tool allowlist resolution
  3. config_builder — secret resolution, circuit breaker, transport rendering
  4. Tenant isolation — config build never crosses orgs
  5. handle_replies routing — _run_claude routes to MCP runner only when
     a campaign opts in via mcp_servers, otherwise stays on legacy path
"""
import json
import os
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from campaigns.mcp import config_builder
from campaigns.mcp.registry import default_tools_for, DEFAULT_TOOL_ALLOWLIST
from campaigns.models import (
    Campaign, MCPActionLog, MCPServer, MCPSession, OrgMCPConnection,
    Organization, Product,
)


class RegistryTests(TestCase):

    def test_taggiq_has_safe_default_allowlist(self):
        tools = default_tools_for('taggiq')
        self.assertIn('whoami', tools)
        self.assertIn('search_products', tools)
        self.assertIn('get_quote', tools)
        # Phase A keeps writes off until prompt guardrails ship
        self.assertNotIn('create_quote_draft', tools)
        # request_send_quote is the canonical "never auto" tool
        self.assertNotIn('request_send_quote', tools)

    def test_unknown_server_returns_empty_default(self):
        self.assertEqual(default_tools_for('not-real'), [])


class ConfigBuilderTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Skill', slug='skill-mcp')
        cls.other_org = Organization.objects.create(name='Other', slug='other-mcp')
        cls.taggiq_server = MCPServer.objects.create(
            slug='taggiq',
            display_name='TaggIQ',
            transport='http',
        )

    def _mk_conn(self, *, organization=None, slug='taggiq', secret_ref='TEST_KEY',
                 url='https://api.taggiq.test/mcp', is_active=True,
                 last_health_status='unknown', last_health_check_at=None,
                 enabled_tools=None):
        return OrgMCPConnection.objects.create(
            organization=organization or self.org,
            server=self.taggiq_server,
            slug=slug,
            auth_secret_ref=secret_ref,
            connection_config={'url': url},
            enabled_tools=enabled_tools or [],
            is_active=is_active,
            last_health_status=last_health_status,
            last_health_check_at=last_health_check_at,
        )

    def test_empty_allowed_slugs_returns_no_config(self):
        self._mk_conn()
        with patch.dict(os.environ, {'TEST_KEY': 'sk-x'}):
            r = config_builder.build_for_org(self.org, [])
        self.assertIsNone(r.config_path)
        self.assertEqual(r.reason, 'no_servers_requested')

    def test_loads_active_connection_with_resolved_secret(self):
        self._mk_conn()
        with patch.dict(os.environ, {'TEST_KEY': 'sk-skillblend'}):
            r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertIsNotNone(r.config_path)
        try:
            with open(r.config_path) as fh:
                payload = json.load(fh)
            self.assertIn('mcpServers', payload)
            self.assertIn('taggiq', payload['mcpServers'])
            entry = payload['mcpServers']['taggiq']
            self.assertEqual(entry['type'], 'http')
            self.assertEqual(entry['url'], 'https://api.taggiq.test/mcp')
            self.assertEqual(entry['headers']['Authorization'], 'Bearer sk-skillblend')
        finally:
            os.unlink(r.config_path)
        self.assertEqual([c.slug for c in r.connections], ['taggiq'])
        # File mode 600 — secrets present, restricted
        self.assertEqual(r.skipped, [])

    def test_skips_connection_with_unresolved_secret(self):
        self._mk_conn(secret_ref='UNSET_KEY_NOT_PRESENT')
        # Make sure env doesn't have it
        os.environ.pop('UNSET_KEY_NOT_PRESENT', None)
        r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertIsNone(r.config_path)
        self.assertEqual(len(r.skipped), 1)
        self.assertIn('secret_unresolved', r.skipped[0][1])

    def test_circuit_breaker_skips_recently_failed_connection(self):
        # Marked down 5 minutes ago — under the 60-min recovery window
        recent = timezone.now() - timedelta(minutes=5)
        self._mk_conn(last_health_status='down', last_health_check_at=recent)
        with patch.dict(os.environ, {'TEST_KEY': 'sk-x'}):
            r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertIsNone(r.config_path)
        self.assertEqual(r.skipped[0][1], 'circuit_breaker_open')

    def test_circuit_breaker_recovers_after_window(self):
        # Marked down 2 hours ago — should recover
        old = timezone.now() - timedelta(hours=2)
        self._mk_conn(last_health_status='down', last_health_check_at=old)
        with patch.dict(os.environ, {'TEST_KEY': 'sk-x'}):
            r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertIsNotNone(r.config_path)
        os.unlink(r.config_path)

    def test_cross_org_connections_never_load(self):
        self._mk_conn(organization=self.other_org)
        with patch.dict(os.environ, {'TEST_KEY': 'sk-x'}):
            r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertIsNone(r.config_path,
            'A connection on a different Org must never load when building '
            'config for self.org')


class OAuthCLIConnectionTests(TestCase):
    """Connections with auth_type='oauth_cli' don't write to --mcp-config —
    the Claude CLI inherits them from its user-scope OAuth state."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='S', slug='s-oauth')
        cls.taggiq_server = MCPServer.objects.create(
            slug='taggiq', display_name='TaggIQ', transport='http',
        )

    def test_oauth_cli_connection_loads_without_writing_json(self):
        OrgMCPConnection.objects.create(
            organization=self.org, server=self.taggiq_server,
            slug='taggiq', auth_type='oauth_cli',
            cli_user_scope_name='taggiq',
            connection_config={'url': 'https://api.taggiq.com/mcp'},
            is_active=True,
        )
        r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertEqual(r.reason, 'ok_oauth_cli_only')
        self.assertIsNone(r.config_path,
            'OAuth-CLI servers do not need --mcp-config; CLI inherits them')
        self.assertEqual([c.slug for c in r.connections], ['taggiq'],
            'Connection still counts as loaded for audit')

    def test_oauth_cli_without_scope_name_is_skipped(self):
        OrgMCPConnection.objects.create(
            organization=self.org, server=self.taggiq_server,
            slug='taggiq', auth_type='oauth_cli',
            cli_user_scope_name='',  # missing
            connection_config={'url': 'https://api.taggiq.com/mcp'},
            is_active=True,
        )
        r = config_builder.build_for_org(self.org, ['taggiq'])
        self.assertEqual(r.reason, 'no_eligible_connections')
        self.assertEqual(r.skipped[0][1], 'oauth_cli_no_scope_name')

    def test_mixed_oauth_cli_and_static_bearer_writes_only_static(self):
        """When an Org has both an OAuth-CLI server and a static-bearer
        server in the same call, only the bearer one lands in the JSON."""
        # OAuth-CLI: TaggIQ
        OrgMCPConnection.objects.create(
            organization=self.org, server=self.taggiq_server,
            slug='taggiq', auth_type='oauth_cli',
            cli_user_scope_name='taggiq',
            connection_config={'url': 'https://api.taggiq.com/mcp'},
            is_active=True,
        )
        # Static-bearer: a hypothetical second server
        other = MCPServer.objects.create(
            slug='internal_api', display_name='Internal', transport='http',
        )
        OrgMCPConnection.objects.create(
            organization=self.org, server=other,
            slug='internal', auth_type='static_bearer',
            auth_secret_ref='INTERNAL_KEY',
            connection_config={'url': 'https://internal.test/mcp'},
            is_active=True,
        )
        with patch.dict(os.environ, {'INTERNAL_KEY': 'sk-int'}):
            r = config_builder.build_for_org(self.org, ['taggiq', 'internal'])

        self.assertIsNotNone(r.config_path,
            'Static-bearer side must produce a config file')
        try:
            with open(r.config_path) as fh:
                payload = json.load(fh)
            # Only the static-bearer server is in the JSON
            self.assertEqual(list(payload['mcpServers'].keys()), ['internal'])
        finally:
            os.unlink(r.config_path)
        # Both connections counted as loaded for audit
        slugs = sorted(c.slug for c in r.connections)
        self.assertEqual(slugs, ['internal', 'taggiq'])


class HandleRepliesRoutingTests(TestCase):
    """_product_mcp_slugs returns the union across the product's campaigns;
    _run_claude routes to MCP runner only when union is non-empty."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='S', slug='s-route')
        cls.product = Product.objects.create(
            organization=cls.org, name='P', slug='p-route',
        )
        cls.campaign_with_mcp = Campaign.objects.create(
            name='Has MCP',
            product='other',
            product_ref=cls.product,
            from_email='a@example.test',
            from_name='A',
            mcp_servers=['taggiq'],
        )
        cls.campaign_without_mcp = Campaign.objects.create(
            name='No MCP',
            product='other',
            product_ref=cls.product,
            from_email='b@example.test',
            from_name='B',
            mcp_servers=[],
        )

    def test_product_mcp_slugs_returns_union(self):
        from campaigns.management.commands.handle_replies import Command
        cmd = Command()
        slugs = cmd._product_mcp_slugs(self.product)
        self.assertEqual(slugs, ['taggiq'])

    def test_product_mcp_slugs_empty_when_no_campaign_opted_in(self):
        from campaigns.management.commands.handle_replies import Command
        # Strip out the opt-in
        Campaign.objects.filter(pk=self.campaign_with_mcp.pk).update(
            mcp_servers=[]
        )
        cmd = Command()
        slugs = cmd._product_mcp_slugs(self.product)
        self.assertEqual(slugs, [])

    def test_run_claude_uses_legacy_path_when_no_mcp(self):
        """No campaign in this product has mcp_servers — _run_claude must
        use subprocess.run directly (legacy text path)."""
        Campaign.objects.filter(pk=self.campaign_with_mcp.pk).update(
            mcp_servers=[]
        )
        from campaigns.management.commands.handle_replies import Command
        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda s: s
        cmd.style.WARNING = lambda s: s
        cmd.style.ERROR = lambda s: s

        with patch('campaigns.management.commands.handle_replies.subprocess.run') as mock_run, \
             patch('campaigns.mcp.runner.run_with_mcp') as mock_mcp_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='ok', stderr='')
            cmd._run_claude(prompt='hello', model_flag='sonnet',
                            product=self.product)

        self.assertTrue(mock_run.called,
            'Legacy subprocess.run must be invoked when no MCP campaigns')
        self.assertFalse(mock_mcp_run.called)

    def test_run_claude_routes_to_mcp_runner_when_opted_in(self):
        """A campaign in this product has mcp_servers — must route through
        the runner (which then handles subprocess + audit)."""
        from campaigns.management.commands.handle_replies import Command
        from campaigns.mcp.runner import MCPRunResult
        from decimal import Decimal

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda s: s
        cmd.style.WARNING = lambda s: s
        cmd.style.ERROR = lambda s: s

        fake_result = MCPRunResult(
            success=True, text='', cost_usd=Decimal('0.01'),
            servers_loaded=['taggiq'], servers_skipped=[],
        )
        with patch('campaigns.management.commands.handle_replies.subprocess.run') as mock_run, \
             patch('campaigns.mcp.runner.run_with_mcp', return_value=fake_result) as mock_mcp_run:
            cmd._run_claude(prompt='hello', model_flag='sonnet',
                            product=self.product)

        self.assertTrue(mock_mcp_run.called,
            'MCP runner must be invoked when any campaign has mcp_servers')
        self.assertFalse(mock_run.called,
            'Legacy subprocess.run must NOT fire on the MCP path')


class MCPSessionLifecycleTests(TestCase):
    """run_with_mcp creates an MCPSession even when no servers load, and
    finalizes it with cost / duration / outcome."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='X', slug='x-life')

    def test_session_created_with_empty_servers_when_none_loaded(self):
        from campaigns.mcp.runner import run_with_mcp
        # Mock subprocess.run so we don't actually shell out
        fake_proc = MagicMock(returncode=0, stdout='{"result": "ok", "is_error": false, "total_cost_usd": 0, "num_turns": 1}', stderr='')
        with patch('campaigns.mcp.runner.subprocess.run', return_value=fake_proc):
            r = run_with_mcp(
                prompt='hi',
                organization=self.org,
                allowed_slugs=[],
                triggered_by='test',
            )
        self.assertTrue(r.success)
        self.assertEqual(MCPSession.objects.filter(organization=self.org).count(), 1)
        sess = MCPSession.objects.get(organization=self.org)
        self.assertEqual(sess.server_slugs, [])
        self.assertTrue(sess.success)
        self.assertGreaterEqual(sess.duration_ms, 0)

    def test_session_records_failure_on_subprocess_error(self):
        from campaigns.mcp.runner import run_with_mcp
        fake_proc = MagicMock(returncode=2, stdout='', stderr='boom')
        with patch('campaigns.mcp.runner.subprocess.run', return_value=fake_proc):
            r = run_with_mcp(
                prompt='hi',
                organization=self.org,
                allowed_slugs=[],
                triggered_by='test',
            )
        self.assertFalse(r.success)
        self.assertIn('claude_exit_2', r.error)
        sess = MCPSession.objects.filter(organization=self.org).order_by('-created_at').first()
        self.assertFalse(sess.success)
