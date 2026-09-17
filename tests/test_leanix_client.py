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


# ── timeout configuration ─────────────────────────────────────────────────────
def test_urlopen_receives_the_configured_timeout() -> None:
    """Every urlopen call must pass the configured timeout, not None or the old 30s default."""
    cat = LeanIxCatalog("https://x.leanix.net", "t", timeout=2.5)
    calls: list[Any] = []

    def _urlopen(_req: Any, timeout: float | None = None) -> Any:
        calls.append(timeout)
        if len(calls) == 1:
            return _token()
        return _graphql(["Billing"])

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        cat.lookup("Billing", "softwareSystem")

    assert all(t == 2.5 for t in calls), f"expected all 2.5, got {calls}"


def test_socket_timeout_becomes_catalog_error() -> None:
    """A TimeoutError (subclass of OSError) must surface as CatalogError."""
    cat = LeanIxCatalog("https://x.leanix.net", "t")
    with (
        patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")),
        pytest.raises(CatalogError) as exc_info,
    ):
        cat.lookup("Billing", "softwareSystem")
    assert "LeanIX" in str(exc_info.value)


def test_from_env_reads_timeout_seconds() -> None:
    """LEANIX_TIMEOUT_SECONDS must be passed to the constructor."""
    from arb_mcp.infra.leanix.client import from_env

    env = {
        "LEANIX_BASE_URL": "https://x.leanix.net",
        "LEANIX_API_TOKEN": "t",
        "LEANIX_TIMEOUT_SECONDS": "7",
    }
    cat = from_env(env)
    assert cat._timeout == 7.0


def test_from_env_uses_default_timeout_of_10() -> None:
    """When LEANIX_TIMEOUT_SECONDS is absent the default must be 10, not 30."""
    from arb_mcp.infra.leanix.client import from_env

    cat = from_env({"LEANIX_BASE_URL": "https://x.leanix.net", "LEANIX_API_TOKEN": "t"})
    assert cat._timeout == 10.0


def test_from_env_refuses_a_non_positive_timeout() -> None:
    """A zero, negative, nan, or inf timeout is refused with RuntimeError."""
    from arb_mcp.infra.leanix.client import from_env

    for bad in ("0", "-1", "-0.5", "nan", "inf", "-inf"):
        with pytest.raises(RuntimeError, match=r"[Tt]imeout"):
            from_env(
                {
                    "LEANIX_BASE_URL": "https://x.leanix.net",
                    "LEANIX_API_TOKEN": "t",
                    "LEANIX_TIMEOUT_SECONDS": bad,
                }
            )


def test_from_env_refuses_a_non_numeric_timeout() -> None:
    """A non-numeric value is refused with RuntimeError."""
    from arb_mcp.infra.leanix.client import from_env

    with pytest.raises(RuntimeError, match=r"[Tt]imeout"):
        from_env(
            {
                "LEANIX_BASE_URL": "https://x.leanix.net",
                "LEANIX_API_TOKEN": "t",
                "LEANIX_TIMEOUT_SECONDS": "notanumber",
            }
        )
