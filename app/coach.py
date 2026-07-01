"""Moteur d'explication progressive : transforme des signaux VÉRIFIÉS en une
échelle d'indices façon coach. Mise en mots par Claude (ancrée sur les faits),
avec repli sur des gabarits déterministes si aucune clé API n'est disponible.
"""
import json
import os
import re
from typing import List

import chess

from . import explain
from . import signal_detectors as sd

# Haiku par défaut : la reformulation d'indices ancrés ne nécessite pas Opus,
# et c'est ~20x moins cher. Surchargé par la variable d'env CHESS_COACH_MODEL.
MODEL = os.environ.get("CHESS_COACH_MODEL", "claude-haiku-4-5")
# Sortie plafonnée pour garantir le coût : avec Haiku, ~0,2 centime/puzzle
# (≈ 5× sous l'objectif de 1 centime). NB : avec Opus le coût frôle 1 centime —
# garder Haiku pour respecter le budget. 350 suffit (4 indices courts ≈ 200 tokens)
# et raccourcit un peu la génération.
MAX_TOKENS = int(os.environ.get("CHESS_COACH_MAX_TOKENS", "350"))

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


# Thèmes peu informatifs (présents sur presque tous les puzzles) : on les cache.
_THEME_HIDE = {"crushing"}


def themes_fr(themes: str) -> list:
    """Thèmes Lichess (chaîne) -> libellés français (inconnus et bruyants ignorés)."""
    return [THEME_FR[t] for t in (themes or "").split()
            if t in THEME_FR and t not in _THEME_HIDE]


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


# Détecte un « coup » SAN explicite (pièce, capture, roque, promotion) — pas une
# simple case (« e6 ») ni une poussée de pion (« b3 »), pour ne pas sur-rejeter.
_MOVE_RE = re.compile(
    r"O-O-O|O-O|[RDTFC][a-h]?[1-8]?x?[a-h][1-8](?:=[RDTF])?[+#]?"
    r"|[a-h]x[a-h][1-8](?:=[RDTF])?[+#]?|[a-h][1-8]=[RDTF][+#]?"
)


def _norm_move(s: str) -> str:
    return s.replace("+", "").replace("#", "").replace("x", "").replace("=", "").strip()


def _extract_hints_json(text: str) -> List[str]:
    """Extrait la liste d'indices d'une réponse JSON en texte brut.

    Tolère les clôtures markdown (``` / ```json) et les deux formes
    {"hints": [...]} ou [...]. Lève une exception si le format est inexploitable
    (le caller retombe alors sur les indices déterministes).
    """
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s).strip()
    data = json.loads(s)
    hints = data["hints"] if isinstance(data, dict) else data
    if not isinstance(hints, list):
        raise ValueError("format JSON inattendu (ni objet .hints ni tableau)")
    return [str(h).strip() for h in hints if str(h).strip()]


def _hints_consistent(hints: List[str], sans: List[str]) -> bool:
    """Vrai si AUCUN coup cité dans les indices n'est absent de la solution.
    Garde-fou anti-hallucination du LLM (ex. inventer un mat inexistant)."""
    allowed = {_norm_move(s) for s in sans}
    for tok in _MOVE_RE.findall(" ".join(hints)):
        if _norm_move(tok) not in allowed:
            print(f"[coach] indice LLM incohérent (coup '{tok}' hors solution) → repli")
            return False
    return True


# System prompt partagé (appel JSON classique ET appel streaming).
_SYSTEM = (
    "Tu es un entraîneur d'échecs francophone, clair et bienveillant. But : faire "
    "RAISONNER l'élève, pas mémoriser. On te fournit des indices factuels DÉJÀ "
    "VÉRIFIÉS (corrects et centrés sur LA solution) et la ligne solution complète, "
    "pour t'ancrer. Tu n'en produis que 3 indices progressifs. Règles absolues :\n"
    "1. Tu REFORMULES ces indices en un raisonnement de coach fluide. N'affirme QUE "
    "ce qui figure dans la base : n'invente aucun coup, pièce, case ni menace, et "
    "ne mentionne PAS d'autres idées/attaques que celles de la base.\n"
    "2. TUTOIE l'élève (tu, ton, te) — jamais de vouvoiement.\n"
    "3. Français à 100 % ; thèmes en français (« fourchette », pas « fork ») ; "
    "notation française des pièces R/D/T/F/C, jamais K/Q/R/B/N.\n"
    "4. Respecte la PROGRESSION en 3 indices : indice 1 = orientation, ne révèle NI "
    "la case NI le coup ; indice 2 = la faiblesse/le signal clé ; indice 3 = oriente "
    "vers la case/le motif pour DÉBLOQUER l'élève, SANS jamais donner le coup exact "
    "ni révéler la solution (c'est à l'élève de trouver le coup final).\n"
    "5. Concis : 1 à 2 phrases par indice, sans préfixe (« Indice 1 : »…)."
)

_FMT_JSON = ('Réponds UNIQUEMENT avec un objet JSON {"hints": ["…", "…", "…"]} '
             "(exactement 3 chaînes, dans l'ordre des 3 indices), sans aucun texte "
             "ni balise autour.")
_FMT_LINES = ("Réponds avec EXACTEMENT 3 lignes, une par indice, dans l'ordre, sans "
              "numéro ni préfixe ni ligne vide (un indice complet par ligne).")


def _user_payload(side, target_elo, themes, base, sans, fmt_reponse) -> str:
    niveau = ("débutant : sois plus explicite et encourageant"
              if target_elo and target_elo < 1200 else
              "joueur confirmé : sois dense et précis")
    user = {
        "trait": side,
        "niveau_eleve_elo": target_elo,
        "adapter_au_niveau": niveau,
        "themes": themes_fr(themes),
        "indices_factuels_verifies_a_reformuler": base,
        "solution_notation_francaise": sans,
        "consigne": "Rédige 3 indices de coach (tutoiement) en t'appuyant strictement "
                    "sur la base et la progression ci-dessus. Le 3e indice débloque sans "
                    "donner le coup. INTERDIT : citer un coup (notation) absent de "
                    "solution_notation_francaise — n'invente jamais de mat, d'échec ou de "
                    "capture qui n'y figure pas.",
        "format_reponse": fmt_reponse,
    }
    return json.dumps(user, ensure_ascii=False)


def _hint_move_ok(hint: str, sans) -> bool:
    """Vrai si l'indice ne cite aucun coup absent de la solution (per-indice)."""
    allowed = {_norm_move(s) for s in sans}
    return all(_norm_move(t) in allowed for t in _MOVE_RE.findall(hint))


def _clean_hint_line(line: str) -> str:
    """Retire un éventuel préfixe (« 1. », « - », « Indice 1 : ») d'une ligne."""
    return re.sub(r"^(?:indice\s*\d+\s*[:\-.)]?\s*|\d+\s*[.)\-:]\s*|[-•*]\s*)",
                  "", line.strip(), flags=re.I).strip()


def _safe_hint(hint: str, base: List[str], i: int, sans) -> str:
    """Indice validé : s'il cite un coup hors solution, on le remplace par le
    repli déterministe correspondant (garde-fou anti-hallucination per-indice)."""
    if _hint_move_ok(hint, sans):
        return hint
    print(f"[coach] indice {i + 1} incohérent (coup hors solution) → repli")
    return base[i] if i < len(base) else hint


def _claude_hints(board, signals, sans, sol_uci, themes, target_elo) -> List[str]:
    """Demande à Claude de mettre les SIGNAUX VÉRIFIÉS en mots façon coach (non-stream)."""
    import anthropic

    client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY dans l'environnement
    side = "les Blancs" if board.turn == chess.WHITE else "les Noirs"
    # Base VÉRIFIÉE et déjà centrée sur la solution (évite les signaux hors-sujet).
    base = explain.build_hints(board, sol_uci, themes, target_elo, signals)
    user = _user_payload(side, target_elo, themes, base, sans, _FMT_JSON)
    # Sortie en texte brut (JSON demandé dans la consigne) plutôt que décodage
    # contraint json_schema : évite le surcoût de latence du mode structuré, la
    # robustesse étant assurée par le parsing tolérant + repli déterministe.
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0.3,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    u = resp.usage
    # Coût estimé (Haiku 4.5 : 1$/1M in, 5$/1M out). Visible dans les logs Vercel.
    cost = u.input_tokens / 1e6 * 1.0 + u.output_tokens / 1e6 * 5.0
    print(f"[coach] {MODEL} in={u.input_tokens} out={u.output_tokens} "
          f"~${cost:.5f} (~{cost * 92:.3f} centimes EUR)")
    text = next(b.text for b in resp.content if b.type == "text")
    try:
        hints = _extract_hints_json(text)
    except Exception as e:  # JSON illisible → repli déterministe (corrects)
        print(f"[coach] parse JSON échoué → repli déterministe ({e})")
        return base
    # Garde-fou : si le LLM cite un coup hors solution (hallucination), on jette
    # tout et on rend les indices déterministes (corrects).
    if len(hints) < 3 or not _hints_consistent(hints, sans):
        return base
    return hints[:3]


def _claude_hints_stream(board, signals, sans, sol_uci, themes, target_elo):
    """Génère les 3 indices en streaming : yield (i, indice) dès qu'une ligne est
    complète. Chaque indice est validé à la volée (repli per-indice si coup hors
    solution). Le 1er indice s'affiche ainsi ~1 s au lieu d'attendre les 3."""
    import anthropic

    client = anthropic.Anthropic()
    side = "les Blancs" if board.turn == chess.WHITE else "les Noirs"
    base = explain.build_hints(board, sol_uci, themes, target_elo, signals)
    user = _user_payload(side, target_elo, themes, base, sans, _FMT_LINES)
    emitted = 0
    with client.messages.stream(
        model=MODEL, max_tokens=MAX_TOKENS, temperature=0.3,
        system=_SYSTEM, messages=[{"role": "user", "content": user}],
    ) as stream:
        buf = ""
        for chunk in stream.text_stream:
            buf += chunk
            while "\n" in buf and emitted < 3:
                line, buf = buf.split("\n", 1)
                hint = _clean_hint_line(line)
                if not hint:
                    continue
                yield emitted, _safe_hint(hint, base, emitted, sans)
                emitted += 1
        if emitted < 3:  # dernière ligne éventuelle sans « \n » final
            hint = _clean_hint_line(buf)
            if hint:
                yield emitted, _safe_hint(hint, base, emitted, sans)
                emitted += 1
        try:  # coût (usage disponible une fois le flux consommé)
            u = stream.get_final_message().usage
            cost = u.input_tokens / 1e6 * 1.0 + u.output_tokens / 1e6 * 5.0
            print(f"[coach] {MODEL} (stream) in={u.input_tokens} out={u.output_tokens} "
                  f"~${cost:.5f} (~{cost * 92:.3f} centimes EUR)")
        except Exception:
            pass
    # Complète si le modèle a produit moins de 3 indices.
    while emitted < 3:
        yield emitted, base[emitted]
        emitted += 1


def get_hints(puzzle: dict, target_elo: int, force_llm: bool = False) -> List[str]:
    """Renvoie les 3 indices affichés pour un puzzle (avec cache).

    Narrateur Claude désactivé par défaut (économie de tokens) : activé via la
    variable d'env CHESS_COACH_LLM=on, ou ponctuellement via force_llm (tests).
    """
    pid = puzzle["id"]
    # Narrateur Haiku ACTIVÉ par défaut ; mettre CHESS_COACH_LLM=off pour repasser
    # aux gabarits (gratuit). Repli automatique sur gabarits si pas de clé / erreur API.
    env_on = os.environ.get("CHESS_COACH_LLM", "on").lower() in ("on", "1", "true", "yes")
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

    # On n'affiche que 3 indices : le 4e (repli déterministe) révèle la solution.
    hints = hints[:3]
    _HINT_CACHE[ck] = hints
    return hints


def stream_hints(puzzle: dict, target_elo: int, force_llm: bool = False):
    """Émet les 3 indices en NDJSON ({"i":…, "hint":…}\\n), un par ligne, au fil de
    l'eau : le 1er indice part dès qu'il est prêt (~1 s) au lieu d'attendre les 3.

    Alimente le même cache mémoire que get_hints (cache mutualisé entre les deux
    endpoints). Repli déterministe si LLM désactivé / pas de clé / erreur API.
    """
    pid = puzzle["id"]
    env_on = os.environ.get("CHESS_COACH_LLM", "on").lower() in ("on", "1", "true", "yes")
    llm_on = (env_on or force_llm) and bool(os.environ.get("ANTHROPIC_API_KEY"))
    ck = (pid, llm_on)

    def line(i, h):
        return json.dumps({"i": i, "hint": h}, ensure_ascii=False) + "\n"

    if ck in _HINT_CACHE:  # déjà généré : on renvoie instantanément
        for i, h in enumerate(_HINT_CACHE[ck]):
            yield line(i, h)
        return

    board, sol_uci = position_to_solve(puzzle["fen"], puzzle["moves"])
    signals = sd.detect_all(board)
    sans = solution_san_fr(board, sol_uci)
    themes = puzzle.get("themes", "") or ""

    if not llm_on:  # gabarits déterministes (gratuit)
        hints = explain.build_hints(board, sol_uci, themes, target_elo, signals)[:3]
        for i, h in enumerate(hints):
            yield line(i, h)
        _HINT_CACHE[ck] = hints
        return

    collected: List[str] = []
    try:
        for i, h in _claude_hints_stream(board, signals, sans, sol_uci, themes, target_elo):
            collected.append(h)
            yield line(i, h)
    except Exception as e:  # erreur API en cours de flux → on complète en déterministe
        print(f"[coach] stream repli déterministe (erreur API : {e})")
        base = explain.build_hints(board, sol_uci, themes, target_elo, signals)
        for i in range(len(collected), 3):
            collected.append(base[i])
            yield line(i, base[i])
    _HINT_CACHE[ck] = collected[:3]
