"""Accès SQLite aux puzzles."""
import os
import sqlite3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_db_path() -> str:
    """Cherche la base à plusieurs endroits (local et déploiement Vercel)."""
    candidates = [
        os.environ.get("CHESS_DB_PATH"),
        os.path.join(HERE, "data", "puzzles.sqlite"),
        os.path.join(HERE, "puzzles.sqlite"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    # défaut (utilisé pour les messages d'erreur même si absent)
    return os.path.join(HERE, "data", "puzzles.sqlite")


DB_PATH = _resolve_db_path()

# Filtre SQL : nombre de demi-coups dans `moves` >= seuil
_PLIES = "(LENGTH(moves) - LENGTH(REPLACE(moves, ' ', '')) + 1)"


def _connect():
    con = sqlite3.connect(_resolve_db_path())
    con.row_factory = sqlite3.Row
    return con


def db_exists() -> bool:
    return os.path.exists(_resolve_db_path())


def random_puzzle(min_rating: int, max_rating: int, min_plies: int = 0):
    con = _connect()
    try:
        rows = con.execute(
            f"SELECT * FROM puzzles WHERE rating BETWEEN ? AND ? "
            f"AND {_PLIES} >= ? ORDER BY RANDOM() LIMIT 1",
            (min_rating, max_rating, min_plies),
        ).fetchall()
    finally:
        con.close()
    return dict(rows[0]) if rows else None


def get_puzzle(puzzle_id: str):
    con = _connect()
    try:
        row = con.execute("SELECT * FROM puzzles WHERE id = ?", (puzzle_id,)).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


def sample_with_theme(theme: str, limit: int = 5):
    """Pour les tests : puzzles contenant un thème donné."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM puzzles WHERE themes LIKE ? LIMIT ?",
            (f"%{theme}%", limit),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]
