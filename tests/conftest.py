"""Fixtures partagées des tests."""
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import coach, db  # noqa: E402
from app.main import app  # noqa: E402

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover
    TestClient = None


@pytest.fixture(scope="session")
def client():
    if TestClient is None:
        pytest.skip("TestClient indisponible")
    return TestClient(app)


@pytest.fixture(scope="session")
def all_puzzles():
    if not db.db_exists():
        pytest.skip("Base de puzzles absente (scripts/build_db.py)")
    con = sqlite3.connect(db.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM puzzles").fetchall()]
    con.close()
    return rows


def find_puzzle(rows, *, white_to_move=None, n_solver=None, no_promotion=True):
    """Sélectionne un puzzle déterministe selon des critères (pour les tests/e2e)."""
    import chess
    for p in rows:
        board, sol = coach.position_to_solve(p["fen"], p["moves"])
        if not sol:
            continue
        if no_promotion and any(len(m) > 4 for m in sol):
            continue
        if white_to_move is not None and (board.turn == chess.WHITE) != white_to_move:
            continue
        if n_solver is not None and (len(sol) + 1) // 2 != n_solver:
            continue
        return p, board, sol
    return None, None, None
