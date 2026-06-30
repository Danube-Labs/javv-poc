"""Scaffold smoke test — proves the package imports and the toolchain runs green.
Replaced by real unit tests as the M0 slices land (normalize, adapters, envelope, …)."""

import scanner


def test_package_imports() -> None:
    assert scanner.__version__ == "0.1.0"
