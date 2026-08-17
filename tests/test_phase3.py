import json
from pathlib import Path

from app.engines.themes import (
    load_theme_graph,
    score_themes,
    themes_for_symbol,
)


def test_load_theme_graph() -> None:
    graph = load_theme_graph()
    assert graph.get("version") == 1
    assert len(graph.get("themes", [])) >= 1


def test_themes_for_symbol_hal() -> None:
    themes = themes_for_symbol("HAL")
    assert any(theme["id"] == "defense_indigenization" for theme in themes)


def test_score_themes_writes_payload(monkeypatch, tmp_path: Path) -> None:
    from app.engines import themes as themes_module

    scores_dir = tmp_path / "scores"
    overrides_dir = tmp_path / "overrides"
    scores_dir.mkdir()
    overrides_dir.mkdir()
    monkeypatch.setattr(themes_module, "theme_scores_dir", lambda: scores_dir)
    monkeypatch.setattr(themes_module, "theme_overrides_dir", lambda: overrides_dir)

    score, reasons, scenarios = score_themes("HAL")
    assert score > 0
    assert reasons
    assert "bull" in scenarios
    assert "base" in scenarios
    assert "bear" in scenarios

    saved = json.loads((scores_dir / "HAL.json").read_text(encoding="utf-8"))
    assert saved["symbol"] == "HAL"
    assert saved["score"] == score


def test_theme_override_boosts_score(monkeypatch, tmp_path: Path) -> None:
    from app.engines import themes as themes_module

    scores_dir = tmp_path / "scores"
    overrides_dir = tmp_path / "overrides"
    scores_dir.mkdir()
    overrides_dir.mkdir()
    monkeypatch.setattr(themes_module, "theme_scores_dir", lambda: scores_dir)
    monkeypatch.setattr(themes_module, "theme_overrides_dir", lambda: overrides_dir)

    (overrides_dir / "HAL.json").write_text(
        json.dumps({"rubric": {"order_book_visibility": 5}}),
        encoding="utf-8",
    )
    score, reasons, _ = score_themes("HAL")
    assert any("Manual override" in reason["text"] for reason in reasons)
    assert score >= 3.0
