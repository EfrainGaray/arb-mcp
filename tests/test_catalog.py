"""Catalog reconciliation against a fake source of truth — no network."""

from arb_mcp.application.check_catalog import CatalogMatch, CatalogReport, check_catalog
from arb_mcp.application.ports import CatalogEntry
from arb_mcp.domain.loading import load


class FakeCatalog:
    def __init__(self, known: set[str]) -> None:
        self._known = known  # set of names present in the catalog

    def lookup(self, name: str, kind: str) -> CatalogEntry | None:  # noqa: ARG002 - CatalogPort
        if name in self._known:
            return CatalogEntry(catalog_id=f"fs-{name}", name=name, type="Application")
        return None


C4 = load(open("tests/fixtures/simple.dsl").read())  # user, sys(+web container)


def test_known_and_unknown_are_split() -> None:
    report = check_catalog(C4, FakeCatalog({"System"}))  # System known, Web not
    assert any(m.name == "System" and m.known for m in report.checked)
    assert any(m.name == "Web App" and not m.known for m in report.checked)
    known = report.known
    assert known[0].entry is not None
    assert known[0].entry.catalog_id == "fs-System"


def test_persons_are_not_catalog_components() -> None:
    report = check_catalog(C4, FakeCatalog(set()))
    names = {m.name for m in report.checked}
    assert "User" not in names  # a person is not a catalog fact sheet


def test_coverage_is_reported() -> None:
    full = check_catalog(C4, FakeCatalog({"System", "Web App"}))
    assert full.coverage == 1.0
    assert full.to_dict()["checked"] == 2


def test_to_dict_keys_are_unchanged() -> None:
    """Wire contract: exact key set for one known and one unknown entry."""
    report = check_catalog(C4, FakeCatalog({"System"}))
    d = report.to_dict()
    # top-level keys
    assert set(d.keys()) == {"checked", "known", "unknown", "coverage"}
    # known entry keys
    known_entry = d["known"][0]
    assert set(known_entry.keys()) == {"id", "name", "type", "catalog_id", "catalog_name"}
    # unknown entry keys (no catalog_id / catalog_name)
    unknown_entry = d["unknown"][0]
    assert set(unknown_entry.keys()) == {"id", "name", "type"}


def test_catalog_match_known_property() -> None:
    entry = CatalogEntry(catalog_id="x", name="X", type="Application")
    known = CatalogMatch(id="x", name="X", type="softwareSystem", entry=entry)
    unknown = CatalogMatch(id="y", name="Y", type="softwareSystem", entry=None)
    assert known.known is True
    assert unknown.known is False


def test_catalog_report_properties() -> None:
    entry = CatalogEntry(catalog_id="k1", name="K", type="Application")
    m1 = CatalogMatch(id="k", name="K", type="softwareSystem", entry=entry)
    m2 = CatalogMatch(id="u", name="U", type="container", entry=None)
    report = CatalogReport(checked=(m1, m2))
    assert len(report.known) == 1
    assert len(report.unknown) == 1
    assert report.known[0].name == "K"
    assert report.coverage == 0.5
