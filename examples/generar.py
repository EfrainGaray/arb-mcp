"""Generate the diagrams in examples/out/ by ASKING THE MCP SERVER, over real stdio.

Calling the application layer from Python proves the library works and nothing
about the server. This spawns `arb-mcp` as a subprocess, speaks MCP to it, and
writes exactly what the tools return.

    python examples/generar.py
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

FUENTE = pathlib.Path("examples/arb-mcp.json")
SALIDA = pathlib.Path("examples/out")


def texto(resultado) -> str:
    if resultado.is_error:
        raise SystemExit(f"la herramienta fallo: {resultado.content}")
    partes = [c.text for c in resultado.content if c.type == "text"]
    if not partes:
        raise SystemExit(f"sin contenido de texto: {resultado.content}")
    return "".join(partes)


def escribir(destino: pathlib.Path, contenido: str) -> None:
    """Write with a trailing newline: a text file in this repository ends in one,
    and without it the committed copy and a fresh run differ by that byte."""
    destino.write_text(contenido if contenido.endswith("\n") else contenido + "\n")


async def main() -> None:
    fuente = FUENTE.read_text()
    SALIDA.mkdir(exist_ok=True)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "arb_mcp.infra.mcp.stdio_server"]
    )
    errlog = open(SALIDA.parent / "servidor.err", "w")
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            print("herramientas:", [t.name for t in (await s.list_tools()).tools])

            # 1. the gate. No verdict, no diagram.
            veredicto = json.loads(texto(await s.call_tool("validate_model", {"source": fuente})))
            print(f"validate_model -> may_merge={veredicto['may_merge']} "
                  f"hallazgos={len(veredicto['findings'])}")
            if not veredicto["may_merge"]:
                for f in veredicto["findings"]:
                    print("   ", f["severity"], f["rule"], f["subject"])
                raise SystemExit(1)

            # 2. one call per surface; the views come back already split by level.
            for destino, ext, clave in (("drawio", "drawio", "xml"), ("mermaid", "mmd", "mermaid")):
                salida = json.loads(
                    texto(await s.call_tool("convert_model", {"source": fuente, "to": destino}))
                )
                for v in salida["views"]:
                    nombre = f"arb-mcp-{v['level'].lower()}-{v['scope']}.{ext}"
                    escribir(SALIDA / nombre, v[clave])
                print(f"convert_model to={destino} -> "
                      f"{[v['level'] + ':' + v['scope'] for v in salida['views']]}")

            dsl = texto(await s.call_tool("convert_model", {"source": fuente, "to": "structurizr"}))
            escribir(SALIDA / "arb-mcp.dsl", dsl)
            print(f"convert_model to=structurizr -> arb-mcp.dsl ({len(dsl)} chars)")
    errlog.close()


asyncio.run(main())
