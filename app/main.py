"""API FastAPI du coach d'échecs."""
import html
import os
from datetime import datetime, timezone

import chess
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import coach, db, explain, store

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

app = FastAPI(title="Chess Mentor — coach de raisonnement")


@app.get("/api/puzzle")
def get_puzzle(min_rating: int = 600, max_rating: int = 2200, min_plies: int = 0,
               id: str | None = None):
    if not db.db_exists():
        raise HTTPException(503, "Base absente. Lance d'abord scripts/build_db.py.")
    # id explicite (lien partageable / tests déterministes) sinon tirage aléatoire.
    puz = db.get_puzzle(id) if id else db.random_puzzle(min_rating, max_rating, min_plies)
    if not puz:
        raise HTTPException(404, "Aucun puzzle dans ces critères.")
    board, solution = coach.position_to_solve(puz["fen"], puz["moves"])
    return {
        "id": puz["id"],
        "fen": board.fen(),  # position À RÉSOUDRE (1er coup adverse déjà joué)
        "rating": puz["rating"],
        "themes": coach.themes_fr(puz["themes"]),
        "side_to_move": "w" if board.turn == chess.WHITE else "b",
        "n_solver_moves": (len(solution) + 1) // 2,  # nombre de coups à trouver
    }


class Attempt(BaseModel):
    id: str
    uci: str          # ex. "f3e5" ou "e7e8q"
    ply: int = 0      # quel coup du solveur (0-based)


@app.post("/api/attempt")
def post_attempt(a: Attempt):
    puz = db.get_puzzle(a.id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    board, solution = coach.board_before_solver_move(puz["fen"], puz["moves"], a.ply)
    idx = 2 * a.ply
    if idx >= len(solution):
        raise HTTPException(400, "Puzzle déjà résolu (ply hors limite).")

    expected = solution[idx]
    correct = a.uci == expected
    if not correct:
        try:
            legal = chess.Move.from_uci(a.uci) in board.legal_moves
        except ValueError:
            legal = False
        return {"correct": False, "legal": legal}

    # Coup correct : on le joue, puis la réponse adverse s'il en reste une.
    board.push_uci(expected)
    result = {"correct": True, "next_ply": a.ply + 1}
    # Explication du coup joué (et de la réponse adverse) — déterministe.
    board0 = chess.Board(puz["fen"])
    board0.push_uci(puz["moves"].split()[0])
    notes = explain.line_notes(board0, solution)
    parts = [notes[idx]] if idx < len(notes) else []
    if idx + 1 < len(notes):
        parts.append(notes[idx + 1])
    result["explain"] = " ".join(parts)
    if idx + 1 < len(solution):
        reply = solution[idx + 1]
        reply_move = chess.Move.from_uci(reply)
        result["opponent_uci"] = reply
        result["opponent_san"] = coach.to_french_san(board.san(reply_move))
        board.push(reply_move)
    # Fini s'il ne reste plus de coup solveur après celui-ci.
    result["done"] = (idx + 2) >= len(solution)
    if result["done"]:
        # Ligne complète en SAN pour l'affichage final.
        b2, sol = coach.position_to_solve(puz["fen"], puz["moves"])
        result["line_san"] = coach.solution_san_fr(b2, sol)
    return result


class HintReq(BaseModel):
    id: str
    level: int  # 1..4
    target_elo: int | None = None


@app.get("/api/solution")
def get_solution(id: str):
    """Ligne complète (coups solveur + réponses adverses) pour le rejeu visuel."""
    puz = db.get_puzzle(id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    board, solution = coach.position_to_solve(puz["fen"], puz["moves"])
    return {"uci": solution, "san": coach.solution_san_fr(board, solution),
            "notes": explain.line_notes(board, solution)}


@app.post("/api/hint")
def post_hint(req: HintReq):
    puz = db.get_puzzle(req.id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    target = req.target_elo or puz["rating"]
    hints = coach.get_hints(puz, target)
    lvl = max(1, min(req.level, len(hints)))
    return {"level": lvl, "total_levels": len(hints), "hint": hints[lvl - 1]}


@app.get("/api/hints")
def get_all_hints(id: str, target_elo: int | None = None):
    """Les 4 indices en un seul appel (1 seule requête Claude par puzzle si activé)."""
    puz = db.get_puzzle(id)
    if not puz:
        raise HTTPException(404, "Puzzle introuvable.")
    target = target_elo or puz["rating"]
    return {"hints": coach.get_hints(puz, target)}


class Feedback(BaseModel):
    text: str = ""
    vote: str | None = None          # "up" | "down" | None
    puzzle_id: str | None = None
    level: str | None = None


@app.post("/api/feedback")
def post_feedback(fb: Feedback, request: Request):
    """Enregistre un retour utilisateur (texte + vote + contexte) dans Vercel KV."""
    text = (fb.text or "").strip()[:2000]
    vote = fb.vote if fb.vote in ("up", "down") else None
    if not text and not vote:
        raise HTTPException(400, "Retour vide.")
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": text,
        "vote": vote,
        "puzzle_id": (fb.puzzle_id or "")[:32],
        "level": (fb.level or "")[:32],
        "ua": (request.headers.get("user-agent") or "")[:200],
    }
    stored = store.push_feedback(record)
    if not stored:
        print(f"[feedback] (KV désactivé) {record}")
    return {"ok": True, "stored": stored}


@app.get("/api/feedback/list", response_class=HTMLResponse)
def list_feedback(key: str = ""):
    """Page admin : liste des retours. Protégée par FEEDBACK_ADMIN_KEY."""
    admin = os.environ.get("FEEDBACK_ADMIN_KEY")
    if not admin or key != admin:
        raise HTTPException(403, "Accès refusé.")
    items = store.list_feedback()
    note = "" if store.kv_enabled() else "<p>⚠️ Vercel KV non configuré : aucun retour stocké.</p>"
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(it.get('ts', ''))}</td>"
        f"<td style='text-align:center'>{'👍' if it.get('vote') == 'up' else '👎' if it.get('vote') == 'down' else ''}</td>"
        f"<td>{html.escape(it.get('puzzle_id', ''))}</td>"
        f"<td>{html.escape(it.get('level', ''))}</td>"
        f"<td>{html.escape(it.get('text', ''))}</td>"
        "</tr>"
        for it in items
    ) or "<tr><td colspan='5'>Aucun retour pour l'instant.</td></tr>"
    return (
        "<!doctype html><meta charset='utf-8'><title>Retours — Chess Mentor</title>"
        "<style>body{font:14px system-ui;background:#161616;color:#eee;padding:24px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #333;padding:8px;"
        "text-align:left;vertical-align:top}th{background:#222}tr:nth-child(even){background:#1d1d1d}</style>"
        f"<h1>Retours ({len(items)})</h1>{note}"
        "<table><tr><th>Date (UTC)</th><th>Vote</th><th>Puzzle</th><th>Niveau</th><th>Message</th></tr>"
        f"{rows}</table>"
    )


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
