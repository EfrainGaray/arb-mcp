# arb-mcp — API

Every call and response below is **captured from the running server** over the MCP stdio protocol, not written by hand. Regenerate with `python docs/gen_api.py`.

Transport: stdio. A host (Kiro) calls a tool by name with a JSON arguments object and receives a single text payload — JSON for every tool except `convert_model to=structurizr`, which returns the raw DSL.

## Tools

- **`describe_contract`** — The contract to build a design against: the C4 spec (allowed node and
- **`build_model_tool`** — Assemble a canonical model from drafted C4 elements and validate it.
- **`validate_model`** — Validate a design and report whether it may merge.
- **`convert_model`** — Export a design to another surface. ``to`` is one of: drawio, structurizr.

---

## `describe_contract`

Kiro calls this first to learn the C4 types and schema it must draft against. No arguments.

**Request**
```json
{
  "name": "describe_contract",
  "arguments": {}
}
```

**Response** (spec trimmed to two node types; schema elided)
```json
{
  "spec": {
    "nodeTypes": {
      "person": {
        "description": "A user of the system",
        "contains": []
      },
      "softwareSystem": {
        "description": "A software system",
        "contains": [
          "container"
        ]
      }
    },
    "relationTypes": {
      "uses": {},
      "affects": {
        "description": "Ties a decision to what it decides",
        "from": [
          "decision"
        ]
      }
    }
  },
  "schema": {
    "$comment": "full JSON Schema draft 2020-12 — 6131 bytes, elided here"
  }
}
```

---

## `build_model_tool`

Kiro hands the elements it drafted from the epic; the server injects the fixed C4 spec, validates, and returns the model with its report. A malformed draft returns `{ok:false, error, detail}`.

**Request**
```json
{
  "name": "build_model_tool",
  "arguments": {
    "nodes": [
      {
        "id": "cust",
        "type": "person",
        "name": "Customer",
        "description": "Pays invoices"
      },
      {
        "id": "bill",
        "type": "softwareSystem",
        "name": "Billing",
        "description": "Charges customers",
        "nodes": [
          {
            "id": "api",
            "type": "container",
            "name": "API",
            "description": "REST API",
            "technology": "FastAPI"
          }
        ]
      }
    ],
    "relations": [
      {
        "from": "cust",
        "to": "api",
        "description": "Pays",
        "technology": "HTTPS"
      }
    ],
    "name": "Billing"
  }
}
```

**Response**
```json
{
  "ok": true,
  "model": {
    "version": "1.0",
    "name": "Billing",
    "scope": "system",
    "spec": {
      "nodeTypes": {
        "person": {
          "description": "A user of the system",
          "contains": []
        },
        "softwareSystem": {
          "description": "A software system",
          "contains": [
            "container"
          ]
        },
        "container": {
          "description": "Something deployable",
          "contains": [
            "component"
          ]
        },
        "component": {
          "description": "A part inside a container",
          "contains": []
        },
        "deploymentNode": {
          "description": "Where something runs"
        },
        "infrastructureNode": {
          "description": "Load balancer, firewall, DNS",
          "contains": []
        },
        "decision": {
          "description": "Decision record",
          "contains": [],
          "requires": [
            "status"
          ]
        }
      },
      "relationTypes": {
        "uses": {},
        "affects": {
          "description": "Ties a decision to what it decides",
          "from": [
            "decision"
          ]
        }
      }
    },
    "nodes": [
      {
        "id": "cust",
        "type": "person",
        "name": "Customer",
        "description": "Pays invoices"
      },
      {
        "id": "bil
…  (truncado)
```

---

## `validate_model`

The merge gate. `source` may be canonical JSON or Structurizr DSL — format detected.

**Request**
```json
{
  "name": "validate_model",
  "arguments": {
    "source": "<canonical model JSON>"
  }
}
```

**Response**
```json
{
  "may_merge": false,
  "blocking_count": 2,
  "findings": [
    {
      "severity": "ERROR",
      "rule": "model.softwareSystem.documentation",
      "message": "The softwareSystem \"Billing\" holds 1 elements inside, but is not documented.",
      "blocking": true
    },
    {
      "severity": "ERROR",
      "rule": "model.softwareSystem.decisions",
      "message": "The softwareSystem \"Billing\" holds elements inside, but no decision backs it.",
      "blocking": true
    }
  ]
}
```

**Response when the source is not a valid model**
```json
{
  "may_merge": false,
  "error": "invalid_model",
  "detail": "No terminal matches 'g' in the current parser context, at line 1 col 1\n\ngarbage {{{\n^\nExpected one of: \n\t* MODEL\n"
}
```

---

## `convert_model`

Exports a design. `to` ∈ {`drawio`, `structurizr`}. drawio returns SEPARATE C4 views (one C1, one C2 per system, one C3 per container), never tabs.

**Request** (drawio)
```json
{
  "name": "convert_model",
  "arguments": {
    "source": "<model or DSL>",
    "to": "drawio"
  }
}
```

**Response** (first view's XML truncated; the rest summarized)
```json
{
  "views": [
    {
      "level": "C1",
      "scope": "system-landscape",
      "name": "Billing — C1 System Context",
      "xml": "<mxfile host=\"arb-mcp\"><diagram name=\"C1 System Context\"><mxGraphModel dx=\"800\" dy=\"600\" grid=\"1\" gridSize=\"10\" guides=\"1\" tooltips=\"1\" connect=\"1\" arrows=\"1\" fold=\"1\" page=\"1\" pageScale=\"1\" pageWidth=\"850\" pageHeight=\"1100\" math=\"0\" shadow=\"0\"><root><mxCell id=\"0\"/><mxCell id=\"1 …  (truncado)"
    },
    {
      "level": "C2",
      "scope": "bill",
      "name": "Billing — C2 Containers",
      "xml": "…"
    }
  ]
}
```

**Request** (structurizr)
```json
{
  "name": "convert_model",
  "arguments": {
    "source": "<model or DSL>",
    "to": "structurizr"
  }
}
```

**Response** (raw Structurizr DSL)
```
workspace "Billing" {
    model {
        cust = person "Customer" "Pays invoices"
        bill = softwareSystem "Billing" "Charges customers" {
            api = container "API" "REST API" "FastAPI"
        }
        cust -> api "Pays" "HTTPS"
    }
    views {
        systemLandscape {
            include *
            autolayout lr
        }
        container bill {
            include *
            autolayout lr
        }
    }
}

```

**Response when `to` is unknown**
```json
{
  "ok": false,
  "error": "unknown format 'png'; known: drawio, structurizr",
  "formats": [
    "drawio",
    "structurizr"
  ]
}
```
