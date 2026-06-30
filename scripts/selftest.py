"""Self-test du proto (sans pytest) : exécute

    python scripts/selftest.py

1. Couverture des détecteurs sur des thèmes Lichess connus.
2. Résolution « joueur parfait » de toute la base via l'API (multi-coups).
"""
import os
import sqlite3
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app import coach, db  # noqa: E402
from app import signal_detectors as sd  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_detectors_cover_themes():
    checks = [
        ("hangingPiece", {"hanging", "underdefended"}),
        ("backRankMate", {"back_rank", "king_box"}),
        ("fork", {"double_attack", "checks"}),
        ("mateIn1", {"checks", "king_box"}),
    ]
    print("== Couverture des détecteurs ==")
    all_ok = True
    for theme, expected in checks:
        puzzles = db.sample_with_theme(theme, 8)
        hit = 0
        for p in puzzles:
            board, _ = coach.position_to_solve(p["fen"], p["moves"])
            if {s.type for s in sd.detect_all(board)} & expected:
                hit += 1
        ok = puzzles and hit == len(puzzles)
        all_ok = all_ok and ok
        print(f"  {theme:14s} {hit}/{len(puzzles)} {'OK' if ok else 'FAIL'}")
    return all_ok


def test_perfect_player():
    print("== Résolution parfaite (multi-coups) via l'API ==")
    con = sqlite3.connect(db.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM puzzles").fetchall()]
    solved = 0
    for p in rows:
        _, solution = coach.position_to_solve(p["fen"], p["moves"])
        ply, ok = 0, True
        while True:
            idx = 2 * ply
            r = client.post(
                "/api/attempt", json={"id": p["id"], "uci": solution[idx], "ply": ply}
            ).json()
            if not r.get("correct"):
                ok = False
                break
            if r["done"]:
                break
            ply = r["next_ply"]
        solved += int(ok)
    print(f"  {solved}/{len(rows)} résolus parfaitement")
    return solved == len(rows)


if __name__ == "__main__":
    if not db.db_exists():
        sys.exit("Base absente : lance d'abord scripts/build_db.py")
    ok1 = test_detectors_cover_themes()
    ok2 = test_perfect_player()
    print("\nRésultat :", "TOUT VERT ✅" if (ok1 and ok2) else "ÉCHEC ❌")
    sys.exit(0 if (ok1 and ok2) else 1)
