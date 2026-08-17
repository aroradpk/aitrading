import pandas as pd

from app.engines.chart_render import chart_path_for_move, render_move_chart
from app.engines.move_detector import detect_moves, save_moves


def _sample_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    prices = [100 + (i * 0.2) for i in range(120)]
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1.5 for p in prices],
            "low": [p - 1.2 for p in prices],
            "close": prices,
            "volume": [1_000_000] * 120,
            "symbol": ["TEST"] * 120,
        },
        index=dates,
    )
    frame.iloc[-1, frame.columns.get_loc("close")] = frame.iloc[-2]["close"] * 1.06
    return frame


def test_render_move_chart_creates_png(tmp_path, monkeypatch) -> None:
    from app.core import paths
    from app.engines import chart_render as chart_module

    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    monkeypatch.setattr(paths, "technical_charts_dir", lambda: charts_dir)
    monkeypatch.setattr(chart_module, "technical_charts_dir", lambda: charts_dir)

    frame = _sample_frame()
    moves = detect_moves(frame, instrument_type="stock")
    assert moves
    move = moves[-1]
    path = render_move_chart(frame, move)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_save_moves_generates_chart_file(tmp_path, monkeypatch) -> None:
    from app.core import paths
    from app.core.config import get_settings
    from app.engines import chart_render as chart_module
    from app.engines import move_detector as move_detector_module

    charts_dir = tmp_path / "charts"
    moves_root = tmp_path / "moves"
    snaps = tmp_path / "snapshots"
    charts_dir.mkdir()
    moves_root.mkdir()
    snaps.mkdir()

    monkeypatch.setattr(paths, "technical_charts_dir", lambda: charts_dir)
    monkeypatch.setattr(paths, "moves_dir", lambda: moves_root)
    monkeypatch.setattr(paths, "technical_snapshots_dir", lambda: snaps)
    monkeypatch.setattr(chart_module, "technical_charts_dir", lambda: charts_dir)
    monkeypatch.setattr(move_detector_module, "moves_dir", lambda: moves_root)
    monkeypatch.setattr(move_detector_module, "technical_snapshots_dir", lambda: snaps)

    settings = get_settings()
    monkeypatch.setattr(settings.charts, "enabled", True)

    frame = _sample_frame()
    moves = detect_moves(frame, instrument_type="stock")
    save_moves("TEST", moves, frame=frame)
    assert any(m.get("chart_file") for m in moves)
    assert chart_path_for_move("TEST", moves[-1]["date"]).exists()
