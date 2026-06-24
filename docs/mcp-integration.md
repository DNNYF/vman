# VMAN MCP integration

VMAN ships a stdio MCP server named `vman-mcp`. It exposes a deliberately small tool surface for Alice/Hermes or any MCP client:

- `list_hosts(limit=100, offset=0)` lists target VPS inventory without credential references, encrypted payloads, or free-form notes.
- `list_recipes()` lists built-in recipe metadata. Raw YAML bodies are not returned.
- `list_jobs(limit=100, offset=0, host_id=None, status=None)` lists recent job summaries.
- `run_recipe(host_id, recipe_name, vars=None, timeout_seconds=600)` runs a low-risk built-in recipe.
- `get_job_status(job_id, include_logs=True, log_limit=200)` returns job status, steps, and redacted logs.

## Safety model

The MCP server is read-mostly and uses the same database, recipe parser, policy engine, and redactor as the HTTP API.

Safety guarantees:

- High-risk and critical recipes never execute through MCP. `run_recipe` returns `approval_required: true` with `executed: false` instead.
- Recipes blocked by policy return `blocked: true` and are not executed.
- Host credential IDs, encrypted credential payloads, and host notes are not exposed by `list_hosts`.
- Job summaries and logs pass through VMAN's redactor before returning to the MCP client.
- Built-in recipe listing omits raw YAML so shell bodies are not echoed during discovery.

MCP execution is intended for low-risk automation such as health checks. Use the dashboard/API approval flow for destructive or production-sensitive actions.

## Running locally

Install the project, then run the stdio server:

```bash
uv run vman-mcp
```

For local development you can also invoke the module directly:

```bash
uv run python -m vman.mcp.server
```

The server reads normal VMAN settings, including `VMAN_DATABASE_URL`, `VMAN_DOTENV_PATH`, and `VMAN_BUILTIN_RECIPES_DIR`.

## Hermes configuration

Once VMAN is installed on the control VPS, register the command with Hermes:

```bash
hermes mcp add vman --command "vman-mcp"
hermes mcp test vman
```

If running from a checkout rather than an installed package, point the command at `uv`:

```bash
hermes mcp add vman --command "uv --directory /home/ubuntu/vman run vman-mcp"
```

## Tool result shapes

`run_recipe` success response:

```json
{
  "job_id": "...",
  "status": "success",
  "exit_code": 0,
  "approval_required": false,
  "executed": true,
  "recipe_name": "healthcheck"
}
```

High-risk response:

```json
{
  "approval_required": true,
  "executed": false,
  "reason": "Recipe install-router has risk_level=high",
  "recipe_name": "install-router",
  "risk_level": "high"
}
```

`get_job_status` returns:

```json
{
  "job": {"id": "...", "status": "success"},
  "steps": [],
  "logs": []
}
```
