workspace "arb-mcp" "El MCP que valida arquitectura como código y la exporta a drawio, Structurizr y Mermaid. Este modelo describe al propio arb-mcp, y sus diagramas se generan con él." {
    model {
        arquitecto = person "Arquitecto" "Escribe el diseño y pide el veredicto desde su editor con MCP"
        pipeline = person "Pipeline de CI" "Pide el veredicto en cada merge request"
        arb = softwareSystem "arb-mcp" "Valida el modelo de arquitectura y lo convierte a las notaciones que cada quien lee" {
            stdio = container "Servidor MCP (stdio)" "describe_contract, build_model, validate_model, convert_model y check_catalog, por el protocolo MCP" "Python, MCP SDK"
            http = container "Adaptador HTTP" "Los mismos casos de uso tras un bearer token o un JWT del IdP, con id de correlación y una línea de auditoría por petición" "FastAPI"
            aplicacion = container "Casos de uso" "Un caso de uso por herramienta; el catálogo y los modelos de lenguaje entran solo por puertos" "Python"
            dominio = container "Dominio" "El modelo tipado, la compuerta determinista y los exportadores. Sin dependencias de framework" "Python, stdlib" {
                modelo = component "Modelo y esquema" "Model, Node, Relation y el JSON Schema normativo: la forma canónica" "dataclasses"
                compuerta = component "Compuerta determinista" "Inspecciones y hallazgos con severidad y sujeto; lo único que puede bloquear un merge" "Python"
                vistas = component "Vistas C4" "Qué se ve en C1, C2 y C3, los externos y la elevación de extremos. Neutral de notación" "Python"
                exportadores = component "Exportadores" "drawio con estilos C4 nativos, Structurizr DSL y Mermaid" "Python"
            }
        }
        leanix = softwareSystem "SAP LeanIX" "El catálogo de arquitectura de la organización: la fuente de la verdad"
        idp = softwareSystem "Proveedor de identidad" "Emite y firma los tokens; Keycloak, Ping o Entra"
        drawio = softwareSystem "drawio" "Donde el diagrama exportado se abre y se edita"
        arquitecto -> stdio "Pide validar y convertir" "MCP"
        pipeline -> http "Pide el veredicto del merge" "HTTPS"
        stdio -> aplicacion "Invoca el caso de uso" "Llamada en proceso"
        http -> aplicacion "Invoca el mismo caso de uso" "Llamada en proceso"
        aplicacion -> dominio "Valida y exporta" "Llamada en proceso"
        aplicacion -> leanix "Contrasta el catálogo" "GraphQL"
        http -> idp "Verifica la firma del token" "JWKS"
        arquitecto -> drawio "Abre y edita el diagrama exportado" "Escritorio"
        compuerta -> modelo "Inspecciona el modelo tipado" "Llamada en proceso"
        exportadores -> vistas "Toma el alcance de cada nivel" "Llamada en proceso"
        vistas -> modelo "Recorre nodos y relaciones" "Llamada en proceso"
    }
    views {
        systemLandscape {
            include *
            autolayout lr
        }
        container arb {
            include *
            autolayout lr
        }
        component dominio {
            include *
            autolayout lr
        }
    }
}
