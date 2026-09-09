"""LeanIX adapter with urlopen mocked — no network. Covers Fable M1/M2/B1."""

import io
import json
import urllib.error
from email.message import Message
from typing import Any
from unittest.mock import patch

import pytest

from arb_mcp.infra.leanix.client import CatalogError, LeanIxCatalog


def _resp(payload: dict[str, Any]) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode())


def _token() -> io.BytesIO:
    return _resp({"access_token": "tok"})


def _graphql(names: list[str]) -> io.BytesIO:
    return _resp(
        {
            "data": {
                "allFactSheets": {
                    "edges": [
                        {"node": {"id": f"fs-{n}", "name": n, "type": "Application"}} for n in names
                    ]
                }
            }
        }
    )


def test_exact_name_match_is_known() -> None:
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    with patch("urllib.request.urlopen", side_effect=[_token(), _graphql(["Billing"])]):
        entry = cat.lookup("Billing", "softwareSystem")
    assert entry is not None and entry.catalog_id == "fs-Billing"


def test_fuzzy_hit_without_exact_name_is_unknown() -> None:
    """M2: fullTextSearch returns 'Ledger Reporting' for 'Ledger' — must be None,
    not a false 'known' with someone else's id."""
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    with patch("urllib.request.urlopen", side_effect=[_token(), _graphql(["Ledger Reporting"])]):
        assert cat.lookup("Ledger", "softwareSystem") is None


def test_case_insensitive_match() -> None:
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    with patch("urllib.request.urlopen", side_effect=[_token(), _graphql(["billing"])]):
        assert cat.lookup("Billing", "softwareSystem") is not None


def test_network_error_becomes_catalog_error() -> None:
    """M1: a network failure must surface as CatalogError, not escape raw."""
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    with (
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")),
        pytest.raises(CatalogError),
    ):
        cat.lookup("Billing", "softwareSystem")


def test_expired_token_triggers_one_reauth() -> None:
    """B1: a 401 clears the cached bearer and retries once."""
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    err401 = urllib.error.HTTPError("u", 401, "unauthorized", Message(), None)
    seq = [_token(), err401, _token(), _graphql(["Billing"])]
    with patch("urllib.request.urlopen", side_effect=seq):
        assert cat.lookup("Billing", "softwareSystem") is not None


def test_empty_result_is_unknown() -> None:
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    with patch("urllib.request.urlopen", side_effect=[_token(), _graphql([])]):
        assert cat.lookup("Billing", "softwareSystem") is None
