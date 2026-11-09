"""Verify offline delivery through the shipped CLIs in both language assignments."""

import pytest
from offline_delivery import run_headless


@pytest.mark.parametrize(
    "alice_language", ["python", "rust"], ids=["alice-python", "alice-rust"]
)
def test_offline_delivery(alice_language):
    run_headless(alice_language)
