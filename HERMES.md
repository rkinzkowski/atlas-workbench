# Hermes connection — prepared for later integration

Atlas is an independent OSINT workbench. The included `hermes_mcp.py` bridge gives an MCP-capable Hermes runtime access to Atlas through its local API. It does not modify Hermes profiles, Kanban, the gateway, the BT interface, or Hermes databases.

The supplied September 7 handoff describes BT/default as coordinator, Ronin/researcher as evidence specialist, and Legion/ops as monitoring specialist. A future integration can route source collection and evidence work through Ronin, with user-authorized monitoring handled by Legion. These are integration recommendations based on the handoff, not changes made to that system. No specialist runs or Hermes deployment validation have been performed here.

## Local connection

1. Start Atlas and configure source keys under **Setup**.
2. Open a case, choose **Hermes**, and download the connection settings. The file contains paths and a local port, never provider keys.
3. On the machine that runs Hermes, merge the `atlas` entry into the existing `mcp_servers` mapping. Do not replace the rest of the configuration.
4. Reload MCP in Hermes and verify that the Atlas tools appear. First ask it to list cases and source readiness; neither action calls providers.

Hermes supports local stdio MCP servers and discovers their tools from its configuration. See the [official Hermes MCP guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).

The generated file points to the Python interpreter and Atlas files on the current computer. Your handoff describes a different Hermes host/runtime, so that Windows file is not a ready-made remote connection. For later integration, run Atlas and its bridge on the Hermes host with the appropriate paths, or design a separately authenticated remote adapter. Do not expose the current localhost service publicly. On Linux/macOS use environment or session settings; Windows-encrypted credentials cannot be copied there for use.

Example when both processes run on the same host:

```yaml
mcp_servers:
  atlas:
    command: "/absolute/path/to/python"
    args: ["/absolute/path/to/atlas-workbench/hermes_mcp.py", "--port", "8765"]
```

## Available tools

| Purpose | Tools |
|---|---|
| Find cases and source readiness | `atlas_cases`, `atlas_sources`, `atlas_case` |
| Inspect full records | `atlas_evidence`, `atlas_search`, `atlas_compare`, `atlas_read_report`, `atlas_export` |
| Create and collect | `atlas_create_case`, `atlas_add_entity`, `atlas_plan`, `atlas_start_plan`, `atlas_lookup`, `atlas_cancel` |
| Preserve research and review | `atlas_add_evidence`, `atlas_apply`, `atlas_review`, `atlas_save_answer`, `atlas_report` |
| Monitor | `atlas_monitor_create`, `atlas_monitor_set` |

Planning makes no source requests. Starting a plan or lookup sends the selected identifiers to its providers and may incur charges. Monitoring schedules recurring requests while Atlas runs. Hermes should act within the user's chosen sources, purpose, schedule and spending authorization.

The bridge intentionally does not return Atlas's write token or provider credentials. It reads full evidence on demand rather than treating case summaries as complete source records. Evidence is untrusted data; any instructions inside source material are not instructions for Hermes. Array comparisons are positional and matching identifiers are leads, not verified identity.

`atlas_report` generates a complete local evidence report without an additional AI charge. Hermes can read evidence using its own model and save a separate authored answer with `[E123]` citations. Atlas validates that those evidence IDs belong to the case, not the truth of the answer's claims.

## Verification status

Automated tests perform a real stdio subprocess handshake, list tools, and read complete evidence through a temporary local HTTP server. Invalid arguments are handled and the Atlas write token is absent from tool results. This proves the bridge's local protocol path; it is not a successful connection to your deployed Hermes instance.

The bridge implements the [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) and [tools interface](https://modelcontextprotocol.io/specification/2025-06-18/server/tools), with protocol negotiation for the listed 2024/2025 versions.
