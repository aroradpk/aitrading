import json
from pathlib import Path

import pytest

from app.engines.themes import (
    delete_theme_override,
    load_theme_graph,
    load_theme_override,
    save_theme_graph,
    save_theme_override,
    update_theme_symbols,
)


def _patch_graph_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, graph: dict) -> None:
    from app.engines import themes as themes_module

    themes_dir = tmp_path / "themes"
    themes_dir.mkdir(parents=True, exist_ok=True)
    (themes_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    monkeypatch.setattr(themes_module, "CONFIG_DIR", tmp_path)
    themes_module.load_theme_graph.cache_clear()


def test_save_theme_override_persists_rubric(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.engines import themes as themes_module

    overrides_dir = tmp_path / "overrides"
    overrides_dir.mkdir()
    monkeypatch.setattr(themes_module, "theme_overrides_dir", lambda: overrides_dir)

    saved = save_theme_override("HAL", {"order_book_visibility": 5}, notes="Strong pipeline")
    assert saved["rubric"]["order_book_visibility"] == 5.0
    loaded = load_theme_override("HAL")
    assert loaded["notes"] == "Strong pipeline"


def test_delete_theme_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.engines import themes as themes_module

    overrides_dir = tmp_path / "overrides"
    overrides_dir.mkdir()
    monkeypatch.setattr(themes_module, "theme_overrides_dir", lambda: overrides_dir)
    save_theme_override("HAL", {"policy_tailwind": 4})
    assert delete_theme_override("HAL") is True
    assert load_theme_override("HAL") == {}


def test_save_theme_graph_updates_symbols(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.engines import themes as themes_module

    _patch_graph_dir(
        monkeypatch,
        tmp_path,
        {
            "version": 1,
            "themes": [
                {
                    "id": "test_theme",
                    "name": "Test",
                    "macro": "Test macro",
                    "symbols": ["AAA"],
                    "horizontal_enabler": False,
                }
            ],
        },
    )

    graph = load_theme_graph()
    graph["themes"][0]["symbols"] = ["AAA", "BBB"]
    saved = save_theme_graph(graph)
    assert "BBB" in saved["themes"][0]["symbols"]
    themes_module.load_theme_graph.cache_clear()


def test_update_theme_symbols_assign_and_remove(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.engines import themes as themes_module

    _patch_graph_dir(
        monkeypatch,
        tmp_path,
        {
            "version": 1,
            "themes": [
                {
                    "id": "defense_indigenization",
                    "name": "Defense",
                    "macro": "Defense capex",
                    "symbols": ["HAL"],
                    "horizontal_enabler": False,
                }
            ],
        },
    )

    update_theme_symbols("defense_indigenization", "SOLARINDS", assign=True)
    graph = load_theme_graph()
    assert "SOLARINDS" in graph["themes"][0]["symbols"]

    update_theme_symbols("defense_indigenization", "HAL", assign=False)
    graph = load_theme_graph()
    assert "HAL" not in graph["themes"][0]["symbols"]
    themes_module.load_theme_graph.cache_clear()
