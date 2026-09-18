# Making diagrams with arb-mcp, from any agent

Install the server, point an agent at it, and work spec first: the design is
written and validated, and the diagrams fall out of it. The agent does the
thinking; these tools are the ground truth, and they are the same from Claude
Code, Codex, Kiro, a shell script or CI.

**The spec is the artefact. A diagram is a projection of it**, generated on
demand and discarded without loss. Section 3 is that method end to end, for an
agent starting from an empty file.

Every command and every output on this page was run against the server in this
repo. The diagrams of arb-mcp's own architecture in `examples/out/` were produced
exactly this way.

## 1. Install

    pipx install arb-mcp            # or: pip install arb-mcp
    arb-mcp                         # speaks MCP over stdio on stdin/stdout

No API key and no LLM: the server calls none. HTTP is the other transport, for
CI; see [AUTH.md](AUTH.md).

## 2. Register it with your agent

Every host reads the same three fields — a command, its arguments, and the
environment. Only the file it lives in differs.

**Claude Code** — `claude mcp add arb -- arb-mcp`, or in `~/.claude.json`:

```json
{ "mcpServers": { "arb": { "command": "arb-mcp", "args": [] } } }
```

**Codex** — in `~/.codex/config.toml`:

```toml
[mcp_servers.arb]
command = "arb-mcp"
args = []
```

**Kiro** — in `~/.kiro/settings/mcp.json`, same shape as Claude Code.

Anything else that speaks MCP works too: the server is a plain stdio process.
Confirm it is wired up by asking the agent to list its tools; five must appear:
`describe_contract`, `build_model_tool`, `validate_model`, `convert_model` and
`check_catalog`.

## 3. The spec comes first, the pictures come out of it

**Never draw first.** The order is not a style preference — a picture drawn
before the design is agreed is a drawing, and it starts rotting the moment it is
saved. The spec is the artefact; every diagram is a projection of it, generated
on demand and thrown away without loss.

An agent starting from nothing walks four steps. Only the second one is
reasoning; the other three are deterministic and the server answers them.

**Step 1 — learn the contract.** `describe_contract()` returns the allowed node
and relation types, the normative JSON Schema, and which surface is canonical.
An agent that calls it does not have to guess the shape:

    nodeTypes: person, softwareSystem, container, component, deploymentNode,
               infrastructureNode, decision
    relationTypes: uses, affects

**Step 2 — draft the design.** This is the agent's own work: read the epic, the
code, the interviews, and write `nodes` and `relations`. Nothing else in the
flow involves judgement.

**Step 3 — turn the draft into a spec, and hold it to the rules.**
`build_model_tool(nodes, relations, name)` injects the fixed type spec, holds the
draft to the schema and returns the model together with its verdict. A first
draft usually does not pass, and that is the tool working:

```
build_model_tool -> ok: True | may_merge: False | hallazgos: 5
    ERROR   model.softwareSystem.documentation  tienda
    ERROR   model.softwareSystem.decisions      tienda
    WARNING model.person.description            cliente
    WARNING model.softwareSystem.description    tienda
```

`ok: True` means the draft became a valid model; `may_merge: False` means the
design has defects the rules can name. A system with containers and no
documentation, and no decision backing it, is rejected on purpose: if the design
does not say *why*, there is nothing worth drawing. The agent fixes those and
calls again until `may_merge` is true. That loop is the whole method.

**Step 4 — only now, the surfaces.** `convert_model(source, to)`. Ask for
`structurizr` first if the spec is what goes in the repository — it is text, it
diffs, it reviews:

```
workspace "Tienda" {
    model {
        cliente = person "Cliente"
        tienda = softwareSystem "Tienda" {
            web = container "Web" "" "Astro"
        }
        cliente -> web "Compra" "HTTPS"
    }
    views {
        systemLandscape { include * ; autolayout lr }
        container tienda { include * ; autolayout lr }
    }
}
```

Then `drawio` for the editable diagrams and `mermaid` for what renders inline on
GitHub and GitLab. All three come from the same validated model, so a diagram
and its verdict cannot drift apart.

**What to keep in version control:** the spec. `examples/arb-mcp.json` is 14 KB
of reviewable text; the nine files in `examples/out/` are regenerated from it
with two calls. If they ever disagree, the spec wins and the exports get rebuilt.

## The two calls, in detail

A model is a JSON document against the normative schema, or Structurizr DSL —
the format is detected. Ask `describe_contract()` first if you are drafting one
and want the allowed types and the schema instead of guessing.

**Call one — the gate.** No verdict, no diagram:

```json
{ "name": "validate_model", "arguments": { "source": "<the model>" } }
```

It answers `{"may_merge": true, "blocking_count": 0, "findings": []}`. If
`may_merge` is false, read `findings`: each one names its `rule` and the
`subject` it fired on. Fix those first — a diagram of a design that does not
hold up is worth less than no diagram.

**Call two — the surfaces.** One call per notation:

```json
{ "name": "convert_model", "arguments": { "source": "<the model>", "to": "drawio" } }
```

`to` is `drawio`, `mermaid` or `structurizr`.

## What comes back

**You do not ask for a C1, a C2 and a C3.** One call returns every view the model
implies: one C1, one C2 per software system that has containers, and one C3 per
container that has components. drawio and mermaid answer with a list, each entry
carrying `level`, `scope`, `name` and its own standalone document:

```json
{ "views": [
  { "level": "C1", "scope": "system-landscape", "name": "arb-mcp — C1 System Context", "xml": "<mxfile …>" },
  { "level": "C2", "scope": "arb",              "name": "arb-mcp — C2 Containers",     "xml": "<mxfile …>" },
  { "level": "C3", "scope": "dominio",          "name": "Dominio — C3 Components",     "xml": "<mxfile …>" }
] }
```

Write each `xml` to its own file named after **level and scope** — naming them by
level alone makes several C3 views overwrite each other. `to="structurizr"`
returns the raw DSL as text, not JSON, because the DSL is one document for the
whole workspace.

**How many diagrams you get is a property of the model, not of the request.**
Want fewer? Describe a container in prose instead of breaking it into components
and its C3 disappears. Want more? Break it down. That is why the three views in
`examples/out/` are three: only `dominio` is drawn as components.

The drawio output is the native C4 shape — `<object>` cells carrying `c4Name`,
`c4Type`, `c4Technology` and `c4Description` with `placeholders="1"`, the
official palette and `metaEdit=1` — so diagrams.net opens them in its C4 editor
as its own, not as generic boxes.

## A worked run

`lab/scratch/por_mcp.py` in this repo does the whole thing over real stdio: it
spawns the server as a subprocess, validates, and writes the three drawio views,
the three mermaid views and the DSL. Its output on this model:

    herramientas: ['describe_contract', 'build_model_tool', 'validate_model', 'convert_model', 'check_catalog']
    validate_model -> may_merge=True hallazgos=0
    convert_model to=drawio -> ['C1:system-landscape', 'C2:arb', 'C3:dominio']
    convert_model to=mermaid -> ['C1:system-landscape', 'C2:arb', 'C3:dominio']
    convert_model to=structurizr -> arb-mcp.dsl (3148 chars)

The core of it, with the error handling left in because it is the part that
matters:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def texto(resultado):
    if resultado.is_error:
        raise SystemExit(f"la herramienta fallo: {resultado.content}")
    return "".join(c.text for c in resultado.content if c.type == "text")

async with stdio_client(StdioServerParameters(command="arb-mcp")) as (read, write):
    async with ClientSession(read, write) as s:
        await s.initialize()
        veredicto = json.loads(texto(await s.call_tool("validate_model", {"source": fuente})))
        if not veredicto["may_merge"]:
            raise SystemExit(veredicto["findings"])
        salida = json.loads(texto(await s.call_tool("convert_model", {"source": fuente, "to": "drawio"})))
        for v in salida["views"]:
            pathlib.Path(f"{v['level'].lower()}-{v['scope']}.drawio").write_text(v["xml"])
```

**Check `is_error` on every result.** A tool that raises comes back as a normal
response with `is_error` set and a one-line message; the detail goes to the
server's stderr, which `stdio_client(..., errlog=…)` lets you capture. Parsing
the content as JSON without that check turns a clear failure into a confusing
`JSONDecodeError` several lines later.

## Hitting it with curl

The HTTP transport mounts the MCP endpoint at `/mcp/mcp`, so a shell can drive it
with no client library at all. Start it and open a session:

    ARB_HTTP_PORT=8000 ARB_HTTP_TOKEN=… arb-mcp-http

```bash
AUTH="Authorization: Bearer $ARB_HTTP_TOKEN"
ACCEPT="Accept: application/json, text/event-stream"
JSON="Content-Type: application/json"

curl -s -D headers.txt -X POST http://127.0.0.1:8000/mcp/mcp -H "$AUTH" -H "$JSON" -H "$ACCEPT" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
       "protocolVersion":"2025-06-18","capabilities":{},
       "clientInfo":{"name":"curl","version":"1"}}}'

SID=$(grep -i mcp-session-id headers.txt | tr -d '\r' | cut -d' ' -f2)

curl -s -X POST http://127.0.0.1:8000/mcp/mcp -H "$AUTH" -H "$JSON" -H "$ACCEPT" \
  -H "mcp-session-id: $SID" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

Then the two calls, with the model as `source`. It is a JSON string, so build the
body with a tool rather than by hand:

```bash
peticion() {  # peticion <tool> [to]
  python3 -c 'import json,sys
a = {"source": open(sys.argv[2]).read()}
if len(sys.argv) > 3:
    a["to"] = sys.argv[3]
print(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call",
                  "params":{"name":sys.argv[1],"arguments":a}}))' "$1" examples/arb-mcp.json "$2"
}

peticion validate_model > req.json
curl -s -X POST http://127.0.0.1:8000/mcp/mcp -H "$AUTH" -H "$JSON" -H "$ACCEPT" \
  -H "mcp-session-id: $SID" --data-binary @req.json
```

`peticion convert_model drawio` builds the body for a surface; swap in `mermaid`
or `structurizr` for the others.

**The reply is an SSE stream, not a bare JSON body.** Each line comes prefixed
`event:` or `data:`; strip the prefix before parsing. This writes each view to
its own file, named after level AND scope:

```bash
curl -s -X POST http://127.0.0.1:8000/mcp/mcp -H "$AUTH" -H "$JSON" -H "$ACCEPT" \
  -H "mcp-session-id: $SID" --data-binary @req.json \
  | sed 's/^data: //' | grep -v '^event:' | grep . \
  | python3 -c '
import json, pathlib, sys
respuesta = json.load(sys.stdin)
for vista in json.loads(respuesta["result"]["content"][0]["text"])["views"]:
    nivel, alcance = vista["level"].lower(), vista["scope"]
    destino = pathlib.Path("arb-mcp-" + nivel + "-" + alcance + ".drawio")
    destino.write_text(vista["xml"])
    print(destino)'
```

    arb-mcp-c1-system-landscape.drawio
    arb-mcp-c2-arb.drawio
    arb-mcp-c3-dominio.drawio

Three surfaces requested this way — drawio, mermaid and structurizr — produce the
files in `examples/out/` byte for byte, which is how that directory is checked.

Three notes that cost time if you find them yourself:

- `Accept` must list **both** `application/json` and `text/event-stream`, or the
  request is refused before it reaches a tool.
- The session id comes back as the `mcp-session-id` response header on
  `initialize`, and every later call must carry it.
- The `notifications/initialized` notification answers `202` with no body. That
  is success, not a silent failure.

There is also a plain REST surface for hosts that do not speak MCP —
`POST /v1/validate` and `POST /v1/convert` with `{"source": …}` — documented in
[AUTH.md](AUTH.md). It runs the same use cases, so the verdict cannot differ.

## From drawio XML to SVG

The XML opens in diagrams.net as it is. To get a self-contained SVG without a
round trip through the app, render it through drawio's own viewer engine and ask
the graph for its SVG — `lab/diagrams/render.mjs` does this with a local copy of
`viewer-static.min.js`, so nothing leaves the machine. Anything else draws C4
shapes that only look similar.

## Related

- [TOOLS.md](TOOLS.md) — what each of the five tools takes, returns and refuses.
- [API.md](API.md) — every call and response, captured from the running server.
- [AUTH.md](AUTH.md) — the HTTP transport, for CI.
- [EJEMPLO-UML.md](EJEMPLO-UML.md) — the same schema carrying UML instead of C4.
