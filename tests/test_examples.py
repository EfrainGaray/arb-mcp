"""The published example is output, and the spec is the artefact.

docs/DIAGRAMS.md tells a reader that everything in examples/out/ is regenerated
from examples/arb-mcp.json. Nothing enforced that, so the two could drift and the
page would go on claiming otherwise. These tests are the enforcement.

They go through the use cases rather than the MCP server: the transport is
covered by tests/test_http_mcp_correlation.py, and what matters here is that the
committed bytes are the ones the exporters produce today.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from arb_mcp.application.convert_model import convert_model, drawio_views
from arb_mcp.application.validate_model import validate_source
from arb_mcp.domain import loading, mermaid

EJEMPLOS = Path(__file__).resolve().parent.parent / "examples"
FUENTE = EJEMPLOS / "arb-mcp.json"
SALIDA = EJEMPLOS / "out"


@pytest.fixture(scope="module")
def fuente() -> str:
    return FUENTE.read_text("utf-8")


def test_the_worked_example_passes_the_gate_it_documents(fuente: str) -> None:
    """A model shipped as the example of a merge gate has to survive that gate."""
    informe = validate_source(fuente)
    assert informe.may_merge, [f.to_dict() for f in informe.blocking]
    assert informe.findings == []


def test_every_committed_drawio_and_mermaid_view_is_what_the_exporter_produces(
    fuente: str,
) -> None:
    """Regenerating writes the same bytes, trailing newline included -- otherwise
    a fresh run shows a diff and nobody can tell drift from formatting."""
    modelo = loading.load(fuente)
    esperado: dict[str, str] = {}
    for vista in drawio_views(modelo):
        esperado[f"arb-mcp-{vista['level'].lower()}-{vista['scope']}.drawio"] = vista["xml"]
    for diagrama in mermaid.to_c4_views(modelo):
        d = diagrama.to_dict()
        esperado[f"arb-mcp-{d['level'].lower()}-{d['scope']}.mmd"] = d["mermaid"]
    esperado["arb-mcp.dsl"] = convert_model(modelo, "structurizr")

    for nombre, contenido in esperado.items():
        archivo = SALIDA / nombre
        assert archivo.exists(), f"{nombre} is documented but not committed"
        con_salto = contenido if contenido.endswith("\n") else contenido + "\n"
        assert archivo.read_text("utf-8") == con_salto, (
            f"{nombre} is stale: run python examples/generar.py"
        )


def test_the_example_ships_exactly_the_views_the_docs_promise(fuente: str) -> None:
    """Three views, because only the domain is broken into components. How many
    diagrams come back is a property of the model, and the docs say so."""
    modelo = loading.load(fuente)
    assert [f"{v['level']}:{v['scope']}" for v in drawio_views(modelo)] == [
        "C1:system-landscape",
        "C2:arb",
        "C3:dominio",
    ]


def test_the_example_declares_no_secrets_and_no_local_paths(fuente: str) -> None:
    """It is published, and a worked example is the first thing anyone copies.

    Matched against secret-shaped VALUES, not vocabulary: this example describes
    an authenticating server, so it says "bearer token" and "password" in prose
    and should go on saying them.
    """
    sospechoso = re.compile(
        r"""(?ix)
        /(?:users|home)/\w              # a path on somebody's machine
        | \b(?:sk-|ghp_|xox[bap]-)[\w-]{8,}   # provider key prefixes
        | \beyJ[\w-]{10,}\.[\w-]{10,}       # a JWT
        | -{5}BEGIN[ A-Z]*PRIVATE\ KEY     # a private key
        | (?:api[_-]?key|secret|password|token)\s*[:=]\s*["\']?[\w-]{12,}
        """
    )
    hallado = sospechoso.search(fuente)
    assert hallado is None, f"the example carries a secret-shaped value: {hallado!r}"
