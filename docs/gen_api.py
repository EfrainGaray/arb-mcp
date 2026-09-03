import asyncio, json, textwrap
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OUT = Path("docs/API.md")

def block(obj, limit=None):
    txt = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    if limit and len(txt) > limit:
        txt = txt[:limit].rstrip() + "\n…  (truncado)"
    return txt

async def call(s, name, args):
    res = await s.call_tool(name, args)
    return res.content[0].text

async def main():
    p = StdioServerParameters(command="python",
        args=["-m", "arb_mcp.infra.mcp.stdio_server"], env={"PYTHONPATH": "src"})
    md = []
    md.append("# arb-mcp — API\n")
    md.append("Every call and response below is **captured from the running server** "
              "over the MCP stdio protocol, not written by hand. Regenerate with "
              "`python docs/gen_api.py`.\n")
    md.append("Transport: stdio. A host (Kiro) calls a tool by name with a JSON "
              "arguments object and receives a single text payload — JSON for every "
              "tool except `convert_model to=arch|structurizr`, which returns the raw "
              "DSL.\n")

    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            md.append("## Tools\n")
            for n in ["describe_contract", "build_model_tool", "validate_model", "convert_model"]:
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
                                f"{len(json.dumps(c['schema']))} bytes, elided here"}}
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
            md.append("The merge gate. `source` may be `.arch`, canonical JSON, or "
                      "Structurizr DSL — format detected.\n")
            md.append("**Request**\n```json\n" +
                      block({"name": "validate_model", "arguments": {"source": "<canonical model JSON>"}}) +
                      "\n```\n")
            v = json.loads(await call(s, "validate_model", {"source": model_json}))
            md.append("**Response**\n```json\n" + block(v, 1200) + "\n```\n")
            md.append("**Response when the source is not a valid model**\n```json\n" +
                      block(json.loads(await call(s, "validate_model", {"source": "garbage {{{"}))) + "\n```\n")

            # 4. convert_model drawio + structurizr
            md.append("---\n\n## `convert_model`\n")
            md.append("Exports a design. `to` ∈ {`drawio`, `arch`, `structurizr`}. "
                      "drawio returns SEPARATE C4 views (one C1, one C2 per system, one "
                      "C3 per container), never tabs.\n")
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

    OUT.write_text("\n".join(md), "utf-8")
    print("escrito:", OUT, OUT.stat().st_size, "bytes")

asyncio.run(main())
