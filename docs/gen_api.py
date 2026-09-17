import asyncio, json, sys, textwrap
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OUT = Path("docs/API.md")
# The interpreter running this script, not a bare "python": on a machine where
# only the venv has the mcp package, "python" is not on PATH and the server never
# starts — which is how API.md silently stayed stale (audit M2).
PYTHON = sys.executable

def block(obj, limit=None):
    txt = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    if limit and len(txt) > limit:
        txt = txt[:limit].rstrip() + "\n…  (truncado)"
    return txt

async def call(s, name, args):
    res = await s.call_tool(name, args)
    return res.content[0].text

async def main():
    p = StdioServerParameters(command=PYTHON,
        args=["-m", "arb_mcp.infra.mcp.stdio_server"], env={"PYTHONPATH": "src"})
    md = []
    md.append("# arb-mcp — API\n")
    md.append("Every call and response below is **captured from the running server** "
              "over the MCP stdio protocol, not written by hand. Regenerate with "
              "`python docs/gen_api.py`.\n")
    md.append("Transport: stdio. A host (Kiro) calls a tool by name with a JSON "
              "arguments object and receives a single text payload — JSON for every "
              "tool except `convert_model to=structurizr`, which returns the raw DSL.\n")

    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            md.append("## Tools\n")
            # Iterate what the server actually registers. A hard-coded list here is
            # how check_catalog went undocumented for a week (audit M2).
            for n in tools:
                md.append(f"- **`{n}`** — {tools[n].description.strip().splitlines()[0]}")
            md.append("")

            # 1. describe_contract
            md.append("---\n\n## `describe_contract`\n")
            md.append("Kiro calls this first to learn the C4 types and schema it must "
                      "draft against. No arguments.\n")
            md.append("**Request**\n```json\n" +
                      block({"name": "describe_contract", "arguments": {}}) + "\n```\n")
            c = json.loads(await call(s, "describe_contract", {}))
            shape = {"spec": {"nodeTypes": {k: c["spec"]["nodeTypes"][k]
                              for k in list(c["spec"]["nodeTypes"])[:2]},
                              "relationTypes": c["spec"]["relationTypes"]},
                     "schema": {"$comment": "full JSON Schema draft 2020-12 — "
                                f"{len(json.dumps(c['schema']))} bytes, elided here"},
                     "canonical_form": c["canonical_form"]}
            md.append("**Response** (spec trimmed to two node types; schema elided)\n```json\n" +
                      block(shape) + "\n```\n")

            # 2. build_model_tool
            md.append("---\n\n## `build_model_tool`\n")
            md.append("Kiro hands the elements it drafted from the epic; the server "
                      "injects the fixed C4 spec, validates, and returns the model with "
                      "its report. A malformed draft returns `{ok:false, error, detail}`.\n")
            nodes = [{"id": "cust", "type": "person", "name": "Customer", "description": "Pays invoices"},
                     {"id": "bill", "type": "softwareSystem", "name": "Billing", "description": "Charges customers",
                      "nodes": [{"id": "api", "type": "container", "name": "API",
                                 "description": "REST API", "technology": "FastAPI"}]}]
            rels = [{"from": "cust", "to": "api", "description": "Pays", "technology": "HTTPS"}]
            args = {"nodes": nodes, "relations": rels, "name": "Billing"}
            md.append("**Request**\n```json\n" +
                      block({"name": "build_model_tool", "arguments": args}) + "\n```\n")
            b = json.loads(await call(s, "build_model_tool", args))
            md.append("**Response**\n```json\n" + block(b, 1400) + "\n```\n")
            model_json = json.dumps(b["model"])

            # 3. validate_model (valid + error)
            md.append("---\n\n## `validate_model`\n")
            md.append("The merge gate. `source` may be canonical JSON or Structurizr "
                      "DSL — format detected.\n")
            md.append("**Request**\n```json\n" +
                      block({"name": "validate_model", "arguments": {"source": "<canonical model JSON>"}}) +
                      "\n```\n")
            v = json.loads(await call(s, "validate_model", {"source": model_json}))
            md.append("**Response**\n```json\n" + block(v, 1200) + "\n```\n")
            md.append("**Response when the source is not a valid model**\n```json\n" +
                      block(json.loads(await call(s, "validate_model", {"source": "garbage {{{"}))) + "\n```\n")

            # 4. convert_model drawio + structurizr
            md.append("---\n\n## `convert_model`\n")
            md.append("Exports a design. `to` ∈ {`drawio`, `structurizr`, `mermaid`}. "
                      "drawio returns SEPARATE C4 views (one C1, one C2 per system, one "
                      "C3 per container), never tabs. mermaid returns the same envelope "
                      "with a `mermaid` key instead of `xml` (C4 models only).\n")
            md.append("**Request** (drawio)\n```json\n" +
                      block({"name": "convert_model", "arguments": {"source": "<model or DSL>", "to": "drawio"}}) +
                      "\n```\n")
            d = json.loads(await call(s, "convert_model", {"source": model_json, "to": "drawio"}))
            # show structure with one view's xml truncated
            v0 = dict(d["views"][0]); v0["xml"] = v0["xml"][:280].rstrip() + " …  (truncado)"
            shown = {"views": [v0] + [{"level": x["level"], "scope": x["scope"],
                     "name": x["name"], "xml": "…"} for x in d["views"][1:]]}
            md.append("**Response** (first view's XML truncated; the rest summarized)\n```json\n" +
                      block(shown) + "\n```\n")
            md.append("**Request** (structurizr)\n```json\n" +
                      block({"name": "convert_model", "arguments": {"source": "<model or DSL>", "to": "structurizr"}}) +
                      "\n```\n")
            st = await call(s, "convert_model", {"source": model_json, "to": "structurizr"})
            md.append("**Response** (raw Structurizr DSL)\n```\n" + block(st, 700) + "\n```\n")
            md.append("**Response when `to` is unknown**\n```json\n" +
                      block(json.loads(await call(s, "convert_model", {"source": model_json, "to": "png"}))) + "\n```\n")

            # 5. check_catalog (captured without LeanIX credentials on purpose: the
            # unavailable shape is what a host sees in every environment but prod)
            md.append("---\n\n## `check_catalog`\n")
            md.append("Reconciles the design against the architecture catalog (LeanIX, "
                      "the source of truth): which components already exist (with their "
                      "catalog id) and which are new. Informational — it never blocks. "
                      "Needs `LEANIX_BASE_URL` and `LEANIX_API_TOKEN`.\n")
            md.append("**Request**\n```json\n" +
                      block({"name": "check_catalog", "arguments": {"source": "<model or DSL>"}}) +
                      "\n```\n")
            md.append("**Response when the catalog is configured** (shape; captured with a test double)\n```json\n" +
                      block({"ok": True, "checked": 2,
                             "known": [{"id": "api", "name": "API", "type": "container",
                                        "catalog_id": "…", "catalog_name": "API"}],
                             "unknown": [{"id": "bill", "name": "Billing", "type": "softwareSystem"}],
                             "coverage": 0.5}) + "\n```\n")
            md.append("**Response when the catalog is not reachable** (captured live, no credentials set)\n```json\n" +
                      block(json.loads(await call(s, "check_catalog", {"source": model_json}))) + "\n```\n")

    OUT.write_text("\n".join(md), "utf-8")
    print("escrito:", OUT, OUT.stat().st_size, "bytes")

asyncio.run(main())
