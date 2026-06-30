"""Moteur d'explication progressive : transforme des signaux VÉRIFIÉS en une
échelle d'indices façon coach. Mise en mots par Claude (ancrée sur les faits),
avec repli sur des gabarits déterministes si aucune clé API n'est disponible.
"""
import json
import os
from typing import List

import chess

from . import explain
from . import signal_detectors as sd

# Haiku par défaut : la reformulation d'indices ancrés ne nécessite pas Opus,
# et c'est ~20x moins cher. Surchargé par la variable d'env CHESS_COACH_MODEL.
MODEL = os.environ.get("CHESS_COACH_MODEL", "claude-haiku-4-5")
# Sortie plafonnée pour garantir le coût : avec Haiku, ~0,2 centime/puzzle
# (≈ 5× sous l'objectif de 1 centime). NB : avec Opus le coût frôle 1 centime —
# garder Haiku pour respecter le budget.
MAX_TOKENS = int(os.environ.get("CHESS_COACH_MAX_TOKENS", "500"))

# Cache mémoire des indices par puzzle (évite de rappeler l'API à chaque niveau)
_HINT_CACHE: dict = {}

# Notation française des pièces : K→R, Q→D, R→T, B→F, N→C (les fichiers a-h restent).
_SAN_FR = str.maketrans({"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"})

# Traductions FRANÇAISES OFFICIELLES de Lichess (translation/dest/puzzleTheme/fr-FR.xml).
THEME_FR = {
    "short": "Court problème", "endgame": "Finale", "middlegame": "Milieu de jeu",
    "crushing": "Écrasant", "mate": "Mat", "advantage": "Avantage",
    "long": "Long problème", "master": "Parties de maîtres", "mateIn1": "Mat en 1",
    "oneMove": "Problème à un coup", "fork": "Fourchette", "mateIn2": "Mat en 2",
    "kingsideAttack": "Attaque sur l'aile roi", "sacrifice": "Sacrifice",
    "pin": "Clouage", "advancedPawn": "Pion avancé", "rookEndgame": "Finale de Tours",
    "veryLong": "Très long problème", "opening": "Ouverture",
    "discoveredAttack": "Attaque à la découverte", "defensiveMove": "Coup défensif",
    "deflection": "Déviation", "mateIn3": "Mat en 3", "attraction": "Attraction",
    "hangingPiece": "Pièce en prise", "pawnEndgame": "Finale de pions",
    "exposedKing": "Roi exposé", "promotion": "Promotion", "quietMove": "Coup silencieux",
    "skewer": "Enfilade", "clearance": "Dégagement", "backRankMate": "Mat du couloir",
    "discoveredCheck": "Échec à la découverte", "queenEndgame": "Finale de Dames",
    "queensideAttack": "Attaque sur l'aile dame", "operaMate": "Mat de l'opéra",
    "masterVsMaster": "Parties jouées entre maîtres", "bishopEndgame": "Finale de Fous",
    "intermezzo": "Coup intermédiaire", "queenRookEndgame": "Dames et Tours",
    "pillsburysMate": "Mat de Pillsbury", "zugzwang": "Zugzwang",
    "trappedPiece": "Pièce enfermée", "knightEndgame": "Finale de Cavaliers",
    "doubleCheck": "Échec double", "smotheredMate": "Mat à l'étouffée",
    "interference": "Interception", "attackingF2F7": "Attaque sur f2 ou f7",
    "morphysMate": "Mat de Morphy", "cornerMate": "Mat en coin", "equality": "Égalité",
    "capturingDefender": "Capturez le défenseur", "swallowstailMate": "Mat du guéridon",
    "epauletteMate": "Mat des épaulettes", "mateIn4": "Mat en 4",
    "hookMate": "Mat du hameçon", "arabianMate": "Mat des Arabes",
    "vukovicMate": "Mat de Vukovic", "dovetailMate": "Mat de Cozio",
    "triangleMate": "Mat du triangle", "anastasiaMate": "Mat d'Anastasie",
    "superGM": "Parties de super GM", "enPassant": "Prise en passant",
    "balestraMate": "Mat de l'arbalète", "killBoxMate": "Mat par mise en boîte",
    "xRayAttack": "Attaque « rayons X »", "blindSwineMate": "Mat des deux tours",
}


def to_french_san(san: str) -> str:
    return san.translate(_SAN_FR)


def themes_fr(themes: str) -> list:
    """Thèmes Lichess (chaîne) -> liste de libellés français (inconnus ignorés)."""
    return [THEME_FR[t] for t in (themes or "").split() if t in THEME_FR]


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


def solution_san_fr(board: chess.Board, solution_uci: List[str]) -> List[str]:
    return [to_french_san(s) for s in solution_san(board, solution_uci)]


def _first_solver_move_san(board: chess.Board, solution_uci: List[str]) -> str:
    if not solution_uci:
        return "?"
    return to_french_san(board.san(chess.Move.from_uci(solution_uci[0])))


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
        "Tu es un entraîneur d'échecs francophone. Ton rôle : apprendre à RAISONNER, "
        "pas à mémoriser. Tu reçois des SIGNAUX déjà vérifiés par un moteur "
        "déterministe et la solution. Règles absolues :\n"
        "1. N'affirme QUE ce qui figure dans les signaux ou la solution fournis ; "
        "n'invente aucun coup, aucune pièce, aucune case.\n"
        "2. Écris en français à 100 % — aucun mot anglais, y compris pour les "
        "thèmes (dis « fourchette », pas « fork »).\n"
        "3. Utilise la notation française des pièces : R (roi), D (dame), T (tour), "
        "F (fou), C (cavalier). Jamais K/Q/R/B/N."
    )
    user = {
        "trait": side,
        "niveau_cible_elo": target_elo,
        "signaux_verifies": facts,
        "themes": themes_fr(themes),
        "solution_notation_francaise": sans,
        "premier_coup_san": first_san,
        "consigne": (
            "Produis exactement 4 indices progressifs, du plus vague au plus précis, "
            "adaptés au niveau cible. Indice 1 = nudge sans rien révéler. Indice 2 = "
            "pointe le(s) signal(aux) clé(s). Indice 3 = oriente vers la case/pièce "
            "sans donner le coup. Indice 4 = donne le premier coup et explique "
            "pourquoi il marche. IMPORTANT : chaque indice est une phrase directe, "
            "SANS préfixe du type 'Niveau 1 :' ou 'Indice 1 :' (l'interface les numérote "
            "déjà). Reste concis (1 à 2 phrases par indice)."
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
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    u = resp.usage
    # Coût estimé (Haiku 4.5 : 1$/1M in, 5$/1M out). Visible dans les logs Vercel.
    cost = u.input_tokens / 1e6 * 1.0 + u.output_tokens / 1e6 * 5.0
    print(f"[coach] {MODEL} in={u.input_tokens} out={u.output_tokens} "
          f"~${cost:.5f} (~{cost * 92:.3f} centimes EUR)")
    text = next(b.text for b in resp.content if b.type == "text")
    hints = json.loads(text)["hints"]
    if len(hints) < 4:
        hints += explain.build_hints(board, sol_uci, themes, target_elo,
                                     signals)[len(hints):]
    return hints[:4]


def get_hints(puzzle: dict, target_elo: int, force_llm: bool = False) -> List[str]:
    """Renvoie les 4 indices pour un puzzle (avec cache).

    Narrateur Claude désactivé par défaut (économie de tokens) : activé via la
    variable d'env CHESS_COACH_LLM=on, ou ponctuellement via force_llm (tests).
    """
    pid = puzzle["id"]
    env_on = os.environ.get("CHESS_COACH_LLM", "off").lower() in ("on", "1", "true", "yes")
    llm_on = (env_on or force_llm) and bool(os.environ.get("ANTHROPIC_API_KEY"))
    ck = (pid, llm_on)
    if ck in _HINT_CACHE:
        return _HINT_CACHE[ck]

    board, sol_uci = position_to_solve(puzzle["fen"], puzzle["moves"])
    signals = sd.detect_all(board)
    sans = solution_san_fr(board, sol_uci)  # notation française pour l'affichage
    themes = puzzle.get("themes", "") or ""

    if llm_on:
        try:
            hints = _claude_hints(board, signals, sans, sol_uci, themes, target_elo)
        except Exception as e:  # repli robuste si l'API échoue
            print(f"[coach] repli déterministe (erreur API : {e})")
            hints = explain.build_hints(board, sol_uci, themes, target_elo, signals)
    else:
        hints = explain.build_hints(board, sol_uci, themes, target_elo, signals)

    _HINT_CACHE[ck] = hints
    return hints
