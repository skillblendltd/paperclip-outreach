"""Registry of known MCP server types and their default tool allowlists.

The MCPServer DB row is the canonical source for which servers exist; this
module supplies the default tool allowlist applied to a fresh
OrgMCPConnection (when its `enabled_tools` list is empty).

Adding a new server type:
  1. Add an MCPServer row (admin or migration data fixture).
  2. Add an entry to DEFAULT_TOOL_ALLOWLIST below.
  3. Default-deny philosophy: list ONLY read-only safe tools by default.
     Write tools require CTO + AI Architect pair review before being
     added to anyone's enabled_tools.

The "request_*" naming convention from TaggIQ is the canonical safe pattern
for server-side approval gates: those create review items, never auto-act.
"""
from __future__ import annotations

# Default per-server allowlists. Read-only tools that we're confident
# about, plus draft-creation tools where the server-side gate is the
# `request_*` naming convention (TaggIQ's review queue). Write tools
# without an approval gate stay disabled by default.
DEFAULT_TOOL_ALLOWLIST: dict[str, list[str]] = {
    'taggiq': [
        # Identity / read-only context
        'whoami',
        # Read-only catalogues
        'search_products',
        'get_product_decorations',
        'list_organization_imprint_methods',
        'list_vendors',
        'get_vendor',
        'list_customers',
        'get_customer',
        # Read-only deal artefacts
        'list_quotes',
        'get_quote',
        'list_orders',
        'get_order',
        'list_invoices',
        'get_invoice',
        # Pure computation (read-only)
        'calculate_decoration_pricing',
        # Phase B (commented out — re-enable when prompt guardrails ship):
        # 'create_quote_draft',
        # 'create_customer_draft',
        # 'request_add_custom_decoration',
        # NEVER auto-enable: 'request_send_quote' (sends to customer)
    ],
    'canva': [
        # Phase C placeholder
    ],
    'gmail': [
        # Phase C placeholder
    ],
    'gdrive': [
        # Phase C placeholder
    ],
}


# Known servers we expect Prakash to seed in the MCPServer table. Used by
# `seed_mcp_servers` management command (Phase B+) and tests.
KNOWN_SERVERS: list[dict[str, str]] = [
    {
        'slug': 'taggiq',
        'display_name': 'TaggIQ POS',
        'transport': 'http',
        'documentation_url': 'https://docs.taggiq.com/mcp',
    },
    # Phase C:
    # {'slug': 'canva', 'display_name': 'Canva', 'transport': 'http', ...},
    # {'slug': 'gmail', 'display_name': 'Gmail', 'transport': 'http', ...},
    # {'slug': 'gdrive', 'display_name': 'Google Drive', 'transport': 'http', ...},
]


def default_tools_for(server_slug: str) -> list[str]:
    """Return the safe-default tool allowlist for a server slug."""
    return list(DEFAULT_TOOL_ALLOWLIST.get(server_slug, []))
