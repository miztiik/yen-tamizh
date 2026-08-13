"""Smoke tests: the backend package imports and its runtime dep is available.

Real tests, no mocks (Holy Law #7). Feature tests land with each pipeline stage.
"""

from pydantic import BaseModel

import yen_tamizh_backend


def test_package_version() -> None:
    assert yen_tamizh_backend.__version__ == "0.1.0"


class _Ping(BaseModel):
    ok: bool


def test_pydantic_available() -> None:
    model = _Ping(ok=True)
    assert model.ok is True
