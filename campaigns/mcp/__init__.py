"""Multi-MCP integration boundary.

Paperclip's reply pipeline talks to MCP servers exclusively through this
package. Direct subprocess invocations of `claude --mcp-config` from any
other module are a BLOCKER at review.

Public API:
  - registry.DEFAULT_TOOL_ALLOWLIST    — per-server safe-default allowlist
  - config_builder.build_for_org(org, campaign_slugs) -> path to JSON file
  - runner.run_with_mcp(prompt, organization, ...) -> MCPRunResult

Architecture rules (CTO-enforced):
  - Auth secrets live in env vars or Secrets Manager. OrgMCPConnection
    stores REFERENCES (e.g. 'TAGGIQ_API_KEY_SKILLBLEND'), never raw values.
  - Tool allowlists default to read-only safe sets. Adding a write tool
    requires CTO + AI Architect pair review.
  - Connection scope is Organization. Cross-org config builds are a
    BLOCKER (config_builder.build_for_org enforces).
  - Per-campaign opt-in (Campaign.mcp_servers JSON list). Empty = no MCP.
"""
