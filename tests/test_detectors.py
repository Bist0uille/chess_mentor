"""Tests des détecteurs de signaux."""
import pytest

from app import coach, db
from app import signal_detectors as sd

THEME_EXPECT = [
    ("hangingPiece", {"hanging", "underdefended"}),
    ("backRankMate", {"back_rank", "king_box"}),
    ("fork", {"double_attack", "checks"}),
    ("mateIn1", {"checks", "king_box"}),
]


@pytest.mark.parametrize("theme,expected", THEME_EXPECT)
def test_theme_coverage(theme, expected):
    puzzles = db.sample_with_theme(theme, 8)
    if not puzzles:
        pytest.skip(f"aucun puzzle '{theme}'")
    for p in puzzles:
        board, _ = coach.position_to_solve(p["fen"], p["moves"])
        types = {s.type for s in sd.detect_all(board)}
        assert types & expected, f"{p['id']} ({theme}) : signaux {types}"


def test_no_crash_on_all(all_puzzles):
    for p in all_puzzles:
        board, _ = coach.position_to_solve(p["fen"], p["moves"])
        signals = sd.detect_all(board)
        for s in signals:
            assert s.short and isinstance(s.short, str)
            assert 1 <= s.severity <= 3
