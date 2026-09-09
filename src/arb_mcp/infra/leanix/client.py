"""CatalogPort adapter over SAP LeanIX (the architecture source of truth).

Two hops, both standard LeanIX: exchange the API token for a bearer token at the
MTM OAuth2 endpoint, then query the Pathfinder GraphQL ``allFactSheets`` with a
full-text search on the component name, filtered to the fact-sheet type. A hit
whose name matches exactly means the component exists; anything else means it
must be registered.

Read-only: it only looks components up, never writes. The bank picks the instance
and token by environment; the code commits to no tenant.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from typing import Any

from ...application.ports import CatalogEntry


class CatalogError(RuntimeError):
    """The catalog could not be reached or answered as expected. A RuntimeError
    so the MCP tool's existing ``except`` reports it as a clean error, never a
    raw traceback."""


# Canonical type -> LeanIX fact-sheet type. Overridable per tenant via env, since
# a bank may model containers as Microservice, ITComponent, etc.
_DEFAULT_TYPE_MAP = {
    "softwareSystem": "Application",
    "container": "Application",
    "component": "Application",
}

_QUERY = """
query($search: String!, $type: String!) {
  allFactSheets(first: 5, filter: {
    facetFilters: [{facetKey: "FactSheetTypes", keys: [$type]}],
    fullTextSearch: $search
  }) { edges { node { id name type } } }
}
"""


class LeanIxCatalog:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        type_map: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        self._base = base_url.rstrip("/")
        self._token = api_token
        self._types = type_map or _DEFAULT_TYPE_MAP
        self._timeout = timeout
        self._bearer: str | None = None
        # The only scheme this client will ever open. Checked once, here, so the
        # two urlopen calls below cannot be pointed at file:// or a custom scheme
        # through a hostile LEANIX_BASE_URL (bandit S310).
        if not self._base.startswith("https://"):
            raise ValueError("LEANIX_BASE_URL must be an https:// URL")

    def _authenticate(self) -> str:
        if self._bearer:
            return self._bearer
        cred = base64.b64encode(f"apitoken:{self._token}".encode()).decode()
        req = urllib.request.Request(  # noqa: S310 - scheme pinned to https in __init__
            f"{self._base}/services/mtm/v1/oauth2/token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
            headers={
                "Authorization": f"Basic {cred}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                self._bearer = str(json.loads(resp.read())["access_token"])
        except (urllib.error.URLError, OSError) as exc:
            raise CatalogError(f"LeanIX authentication failed: {exc}") from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise CatalogError("LeanIX authentication returned no access_token") from exc
        return self._bearer

    def _query(self, name: str, fs_type: str) -> dict[str, Any]:
        payload = {"query": _QUERY, "variables": {"search": name, "type": fs_type}}
        req = urllib.request.Request(  # noqa: S310 - scheme pinned to https in __init__
            f"{self._base}/services/pathfinder/v1/graphql",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._authenticate()}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            body: dict[str, Any] = json.loads(resp.read())
        return body

    def lookup(self, name: str, kind: str) -> CatalogEntry | None:
        fs_type = self._types.get(kind, "Application")
        for attempt in (1, 2):
            try:
                body = self._query(name, fs_type)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == HTTPStatus.UNAUTHORIZED and attempt == 1:
                    self._bearer = None  # token likely expired; re-auth once
                    continue
                raise CatalogError(f"LeanIX query failed: {exc}") from exc
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                raise CatalogError(f"LeanIX query failed: {exc}") from exc
        edges = (((body.get("data") or {}).get("allFactSheets") or {}).get("edges")) or []
        # fullTextSearch is fuzzy: accept only an exact (case-insensitive) name
        # match, or a new component would be reported as an existing one.
        for edge in edges:
            node = edge.get("node") or {}
            if str(node.get("name", "")).casefold() == name.casefold():
                return CatalogEntry(catalog_id=node["id"], name=node["name"], type=node["type"])
        return None


def from_env() -> LeanIxCatalog:
    """Build from LEANIX_BASE_URL and LEANIX_API_TOKEN."""
    base = os.environ.get("LEANIX_BASE_URL")
    token = os.environ.get("LEANIX_API_TOKEN")
    if not base or not token:
        raise RuntimeError(
            "catalog check needs LEANIX_BASE_URL and LEANIX_API_TOKEN in the environment"
        )
    return LeanIxCatalog(base, token)
