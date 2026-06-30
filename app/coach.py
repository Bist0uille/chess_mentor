"""Moteur d'explication progressive : transforme des signaux VÉRIFIÉS en une
échelle d'indices façon coach. Mise en mots par Claude (ancrée sur les faits),
avec repli sur des gabarits déterministes si aucune clé API n'est disponible.
"""
import json
import os
from typing import List

import chess

from . import signal_detectors as sd

MODEL = os.environ.get("CHESS_COACH_MODEL", "claude-opus-4-8")

# Cache mémoire des indices par puzzle (évite de rappeler l'API à chaque niveau)
_HINT_CACHE: dict = {}


def position_to_solve(fen: str, moves_uci: str):
    """Joue le 1er coup (celui de l'adversaire) pour obtenir la position à résoudre.

    Renvoie (board, solution_moves) où solution_moves sont les coups UCI du solveur.
    """
    board = chess.Board(fen)
    uci_list = moves_uci.split()
    board.push_uci(uci_list[0])          # coup d'amorce de l'adversaire
    solution = uci_list[1:]              # le reste = la solution à trouver
    return board, solution


def board_before_solver_move(fen: str, moves_uci: str, k: int):
    """État du plateau juste avant le k-ième coup du solveur (0-based).

    Renvoie (board, solution) où board = position à résoudre + les 2k premiers
    demi-coups de la solution déjà joués (coups solveur pairs, réponses impaires).
    """
    board, solution = position_to_solve(fen, moves_uci)
    for i in range(min(2 * k, len(solution))):
        board.push_uci(solution[i])
    return board, solution


def solution_san(board: chess.Board, solution_uci: List[str]) -> List[str]:
    """Convertit la ligne solution en notation SAN lisible, sans modifier `board`."""
    b = board.copy()
    sans = []
    for uci in solution_uci:
        move = chess.Move.from_uci(uci)
        sans.append(b.san(move))
        b.push(move)
    return sans


def _first_solver_move_san(board: chess.Board, solution_uci: List[str]) -> str:
    if not solution_uci:
        return "?"
    return board.san(chess.Move.from_uci(solution_uci[0]))


def _target_square(solution_uci: List[str]) -> str:
    if not solution_uci:
        return "?"
    return chess.square_name(chess.Move.from_uci(solution_uci[0]).to_square)


def _template_hints(board, signals, sans, sol_uci, themes) -> List[str]:
    """Indices déterministes (sans LLM)."""
    strong = signals[0].short if signals else "Cherche le coup le plus forçant."
    h1 = "Quelque chose cloche dans le camp adverse. Cherche les coups forçants " \
         "(échecs, captures, menaces) avant tout."
    h2 = "Signaux de la position : " + " ".join(s.short for s in signals[:3]) \
        if signals else strong
    h3 = f"Concentre-toi sur la case {_target_square(sol_uci)} : quelle pièce " \
         f"peux-tu y amener ?"
    line = " ".join(sans) if sans else "(ligne indisponible)"
    h4 = f"Solution : {line}."
    return [h1, h2, h3, h4]


def _claude_hints(board, signals, sans, sol_uci, themes, target_elo) -> List[str]:
    """Demande à Claude de mettre les SIGNAUX VÉRIFIÉS en mots façon coach."""
    import anthropic

    client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY dans l'environnement
    side = "les Blancs" if board.turn == chess.WHITE else "les Noirs"
    facts = [s.short for s in signals] or ["(aucun signal saillant détecté)"]
    first_san = _first_solver_move_san(board, sol_uci)

    system = (
        "Tu es un entraîneur d'échecs. Ton rôle : apprendre à RAISONNER, pas à "
        "mémoriser. Tu reçois des SIGNAUX déjà vérifiés par un moteur déterministe "
        "et la solution. Règle absolue : n'affirme QUE ce qui figure dans les "
        "signaux ou la solution fournis ; n'invente aucun coup, aucune pièce, aucune "
        "case. Réponds en français."
    )
    user = {
        "trait": side,
        "niveau_cible_elo": target_elo,
        "signaux_verifies": facts,
        "themes_lichess": themes.split() if themes else [],
        "solution_san": sans,
        "premier_coup_san": first_san,
        "consigne": (
            "Produis exactement 4 indices progressifs, du plus vague au plus précis, "
            "adaptés au niveau cible. Niveau 1 = nudge sans rien révéler. Niveau 2 = "
            "pointe le(s) signal(aux) clé(s). Niveau 3 = oriente vers la case/pièce "
            "sans donner le coup. Niveau 4 = donne le premier coup et explique "
            "pourquoi il marche."
        ),
    }
    schema = {
        "type": "object",
        "properties": {
            "hints": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["hints"],
        "additionalProperties": False,
    }
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=system,
        messages=[{"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    hints = json.loads(text)["hints"]
    if len(hints) < 4:
        hints += _template_hints(board, signals, sans, sol_uci, themes)[len(hints):]
    return hints[:4]


def get_hints(puzzle: dict, target_elo: int) -> List[str]:
    """Renvoie les 4 indices pour un puzzle (avec cache)."""
    pid = puzzle["id"]
    if pid in _HINT_CACHE:
        return _HINT_CACHE[pid]

    board, sol_uci = position_to_solve(puzzle["fen"], puzzle["moves"])
    signals = sd.detect_all(board)
    sans = solution_san(board, sol_uci)
    themes = puzzle.get("themes", "") or ""

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            hints = _claude_hints(board, signals, sans, sol_uci, themes, target_elo)
        except Exception as e:  # repli robuste si l'API échoue
            print(f"[coach] repli templates (erreur API : {e})")
            hints = _template_hints(board, signals, sans, sol_uci, themes)
    else:
        hints = _template_hints(board, signals, sans, sol_uci, themes)

    _HINT_CACHE[pid] = hints
    return hints
