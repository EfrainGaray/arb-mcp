"""CatalogPort adapter over SAP LeanIX (the architecture source of truth).

Two hops, both standard LeanIX: exchange the API token for a bearer token at the
MTM OAuth2 endpoint, then query the Pathfinder GraphQL ``allFactSheets`` with a
full-text search on the component name, filtered to the fact-sheet type. A hit
means the component exists in the catalog; a miss means it must be registered.

Read-only: it only looks components up, never writes. The bank picks the instance
and token by environment; the code commits to no tenant.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from typing import Any

from ...application.ports import CatalogEntry

# Canonical type -> LeanIX fact-sheet type. Overridable per tenant via env, since
# a bank may model containers as Microservice, ITComponent, etc.
_DEFAULT_TYPE_MAP = {
    "softwareSystem": "Application",
    "container": "Application",
    "component": "Application",
}

_QUERY = """
query($search: String!, $type: String!) {
  allFactSheets(first: 1, filter: {
    facetFilters: [{facetKey: "FactSheetTypes", keys: [$type]}],
    fullTextSearch: $search
  }) { edges { node { id name type } } }
}
"""


class LeanIxCatalog:
    def __init__(self, base_url: str, api_token: str,
                 type_map: dict[str, str] | None = None, timeout: float = 30.0):
        self._base = base_url.rstrip("/")
        self._token = api_token
        self._types = type_map or _DEFAULT_TYPE_MAP
        self._timeout = timeout
        self._bearer: str | None = None

    def _authenticate(self) -> str:
        if self._bearer:
            return self._bearer
        cred = base64.b64encode(f"apitoken:{self._token}".encode()).decode()
        req = urllib.request.Request(
            f"{self._base}/services/mtm/v1/oauth2/token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
            headers={"Authorization": f"Basic {cred}",
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            self._bearer = str(json.loads(resp.read())["access_token"])
        return self._bearer

    def lookup(self, name: str, kind: str) -> CatalogEntry | None:
        fs_type = self._types.get(kind, "Application")
        payload = {"query": _QUERY, "variables": {"search": name, "type": fs_type}}
        req = urllib.request.Request(
            f"{self._base}/services/pathfinder/v1/graphql",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self._authenticate()}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            body: dict[str, Any] = json.loads(resp.read())
        edges = (((body.get("data") or {}).get("allFactSheets") or {}).get("edges")) or []
        if not edges:
            return None
        node = edges[0]["node"]
        return CatalogEntry(catalog_id=node["id"], name=node["name"], type=node["type"])


def from_env() -> LeanIxCatalog:
    """Build from LEANIX_BASE_URL and LEANIX_API_TOKEN."""
    base = os.environ.get("LEANIX_BASE_URL")
    token = os.environ.get("LEANIX_API_TOKEN")
    if not base or not token:
        raise RuntimeError(
            "catalog check needs LEANIX_BASE_URL and LEANIX_API_TOKEN in the environment"
        )
    return LeanIxCatalog(base, token)
