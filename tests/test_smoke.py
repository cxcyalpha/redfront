"""Смоук-тест (tools/smoke_test.py) под pytest: каждый раздел - отдельный тест. Запуск: python -m pytest -q"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import smoke_test as smoke  # noqa: E402


@pytest.mark.parametrize("section", smoke.SECTIONS, ids=lambda f: f.__name__.removesuffix("_section"))
def test_section(section, tmp_path):
    smoke.FAILS.clear()
    section(tmp_path)
    assert not smoke.FAILS, "провалы:\n" + "\n".join(smoke.FAILS)
