"""arb-mcp: deterministic C4/DSL validation, conversion and catalog reconciliation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("arb-mcp")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0"
