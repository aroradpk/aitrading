import json
from datetime import date
from pathlib import Path

from app.engines.events import enrich_moves_with_events, score_events
from app.engines.fundamental import import_screener_csv, score_fundamentals


def test_import_screener_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        "Symbol,Book value,ROCE %,Sales growth %\nHAL,850,28,15\n",
        encoding="utf-8",
    )
    imported = import_screener_csv(csv_path)
    assert "HAL" in imported
    assert imported["HAL"]["metrics"]["roce_pct"] == 28


def test_score_fundamentals_from_import(tmp_path: Path, monkeypatch) -> None:
    from app.core import paths

    monkeypatch.setattr(paths, "fundamentals_dir", lambda: tmp_path)
    csv_path = tmp_path / "hal.csv"
    csv_path.write_text(
        "Symbol,Book value,ROCE %,Sales growth %,Profit growth %\nHAL,850,28,15,18\n",
        encoding="utf-8",
    )
    import_screener_csv(csv_path)
    score, reasons = score_fundamentals("HAL")
    assert score > 0
    assert reasons


def test_enrich_moves_with_events(monkeypatch, tmp_path: Path) -> None:
    from app.core import paths
    from app.engines import events as events_module

    nse_dir = tmp_path / "nse"
    nse_dir.mkdir()
    (nse_dir / "HAL.json").write_text(
        json.dumps(
            [
                {
                    "source": "nseindia.com",
                    "type": "board_meeting",
                    "date": "2024-06-10",
                    "title": "Outcome of Board Meeting",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "events_nse_dir", lambda: nse_dir)
    monkeypatch.setattr(
        events_module,
        "load_nse_announcements",
        lambda symbol: json.loads((nse_dir / f"{symbol}.json").read_text()),
    )

    moves = [{"date": "2024-06-11", "move_1d_pct": 6.0}]
    enriched = enrich_moves_with_events("HAL", moves)
    assert enriched[0]["aligned_events"]
    assert enriched[0]["event_reasons"]
