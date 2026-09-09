"""Catalog reconciliation against a fake source of truth — no network."""

from arb_mcp.application.check_catalog import check_catalog
from arb_mcp.application.ports import CatalogEntry
from arb_mcp.domain.loading import load


class FakeCatalog:
    def __init__(self, known):
        self._known = known  # set of names present in the catalog

    def lookup(self, name, kind):  # noqa: ARG002 - signature fixed by CatalogPort
        if name in self._known:
            return CatalogEntry(catalog_id=f"fs-{name}", name=name, type="Application")
        return None


C4 = load(open("tests/fixtures/simple.dsl").read())  # user, sys(+web container)


def test_known_and_unknown_are_split():
    report = check_catalog(C4, FakeCatalog({"System"}))  # System known, Web not
    known = {k["name"] for k in report.known}
    unknown = {u["name"] for u in report.unknown}
    assert "System" in known
    assert "Web App" in unknown
    assert report.known[0]["catalog_id"] == "fs-System"


def test_persons_are_not_catalog_components():
    report = check_catalog(C4, FakeCatalog(set()))
    names = {c["name"] for c in report.known + report.unknown}
    assert "User" not in names  # a person is not a catalog fact sheet


def test_coverage_is_reported():
    full = check_catalog(C4, FakeCatalog({"System", "Web App"}))
    assert full.coverage == 1.0
    assert full.to_dict()["checked"] == 2
