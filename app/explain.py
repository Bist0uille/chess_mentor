"""Moteur d'explication DÉTERMINISTE, centré sur la solution.

On n'appelle aucun LLM : on analyse la ligne solution coup par coup avec
python-chess (échec, capture, sacrifice, coup forcé, menace, motif) et on en
dérive 4 indices progressifs FOCALISÉS sur la solution. Tout est vérifié sur
l'échiquier — aucune invention possible.
"""
from typing import List

import chess

from . import signal_detectors as sd
from .signal_detectors import PIECE_FR, PIECE_VALUE

# Notation française des pièces (K→R, Q→D, R→T, B→F, N→C). Fichiers a-h inchangés.
_SAN_FR = str.maketrans({"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"})


def _fr(san: str) -> str:
    return san.translate(_SAN_FR)


def _name(sq: int) -> str:
    return chess.square_name(sq)


def _fem(piece_type: int) -> bool:
    return piece_type in (chess.QUEEN, chess.ROOK)  # dame, tour → féminin


def _art(piece_type: int) -> str:
    """Article + nom : « le cavalier », « la dame », « la tour »."""
    return ("la " if _fem(piece_type) else "le ") + PIECE_FR[piece_type]


def _poss(piece_type: int) -> str:
    return "ta" if _fem(piece_type) else "ton"


def _accord(piece_type: int, adj_masc: str) -> str:
    """Accorde un adjectif en genre (défendu → défendue)."""
    return adj_masc + "e" if _fem(piece_type) else adj_masc


def _pron(piece_type: int) -> str:
    return "la" if _fem(piece_type) else "le"


# Thèmes tactiques (priorité d'affichage) pour nommer le motif.
_TACTIC_ORDER = [
    "fork", "pin", "skewer", "discoveredAttack", "discoveredCheck", "doubleCheck",
    "deflection", "attraction", "clearance", "interference", "capturingDefender",
    "sacrifice", "backRankMate", "smotheredMate", "hangingPiece", "trappedPiece",
    "xRayAttack", "advancedPawn", "promotion", "enPassant", "intermezzo",
    "quietMove", "exposedKing", "kingsideAttack", "queensideAttack", "zugzwang",
]


def _value(board: chess.Board, sq: int) -> int:
    p = board.piece_at(sq)
    return PIECE_VALUE[p.piece_type] if p else 0


def annotate(board: chess.Board, solution_uci: List[str]) -> dict:
    """Analyse la ligne solution. Renvoie un dossier de faits vérifiés."""
    me = board.turn
    b = board.copy()
    plies = []
    captured_by_me = 0
    captured_by_opp = 0
    won_types = []   # pièces que JE capture
    lost_types = []  # pièces que l'adversaire capture

    for i, uci in enumerate(solution_uci):
        move = chess.Move.from_uci(uci)
        mover = b.piece_at(move.from_square)
        side_is_me = (b.turn == me)
        gives_check = b.gives_check(move)
        # capture (y compris en passant)
        is_capture = b.is_capture(move)
        cap_sq = move.to_square
        cap_type = None
        if is_capture:
            if b.is_en_passant(move):
                cap_type = chess.PAWN
            else:
                tp = b.piece_at(move.to_square)
                cap_type = tp.piece_type if tp else None
            val = PIECE_VALUE.get(cap_type, 0)
            if side_is_me:
                captured_by_me += val
                if cap_type:
                    won_types.append(cap_type)
            else:
                captured_by_opp += val
                if cap_type:
                    lost_types.append(cap_type)
        san_fr = _fr(b.san(move))
        was_check = b.is_check()  # le camp au trait était-il en échec avant ce coup ?

        b.push(move)
        is_mate = b.is_checkmate()

        ply = {
            "i": i, "me": side_is_me, "san": san_fr,
            "from": _name(move.from_square), "to": _name(move.to_square),
            "check": gives_check, "mate": is_mate, "capture": is_capture,
            "cap_type": cap_type, "mover_type": mover.piece_type if mover else None,
            "was_check": was_check,
        }
        plies.append(ply)

    # Interposition (bloquer un échec) et sacrifice.
    for i, ply in enumerate(plies):
        if not ply["me"]:
            continue
        # interposition : on était en échec, on bloque (ni capture ni coup de roi)
        if ply["was_check"] and not ply["capture"] and ply["mover_type"] != chess.KING:
            ply["interpose"] = True
        nxt = plies[i + 1] if i + 1 < len(plies) else None
        gave = PIECE_VALUE.get(ply["mover_type"], 0)
        took = PIECE_VALUE.get(ply["cap_type"], 0) if ply["capture"] else 0
        if not ply.get("interpose") and nxt and (not nxt["me"]) and nxt["capture"] \
                and nxt["to"] == ply["to"] and took < gave:
            ply["sacrifice"] = True

    # Réponses adverses : forcées ?
    bb = board.copy()
    for ply in plies:
        if not ply["me"]:
            n_legal = bb.legal_moves.count()
            in_check = bb.is_check()
            ply["forced"] = (n_legal == 1)
            ply["in_check"] = in_check
        bb.push_uci(solution_uci[ply["i"]])

    # Menace d'un coup tranquille du solveur (1er coup non-échec non-capture)
    threat = None
    first = plies[0] if plies else None
    if first and first["me"] and not first["check"] and not first["capture"]:
        threat = _threat_after(board, solution_uci[0])

    net = captured_by_me - captured_by_opp
    last = plies[-1] if plies else None
    if last and last["mate"]:
        outcome = "mate"
    elif net >= 2:
        outcome = "win_material"
    else:
        outcome = "advantage"

    return {
        "plies": plies, "outcome": outcome, "net_material": net,
        "result": _material_result(won_types, lost_types),
        "threat": threat, "n_solver_moves": (len(solution_uci) + 1) // 2,
    }


def _material_result(won, lost):
    """Décrit le bilan d'un échange en termes d'échecs (dame, qualité, pièce…).
    net = points gagnés (pion 1, mineure 3, tour 5, dame 9)."""
    net = sum(PIECE_VALUE[t] for t in won) - sum(PIECE_VALUE[t] for t in lost)
    if net <= 0:
        return None
    minors = (chess.KNIGHT, chess.BISHOP)
    # gain net de la dame contre la tour (Q pour R) — cas fréquent
    if net == 4 and chess.QUEEN in won and chess.ROOK in lost:
        return "la dame contre la tour"
    # la qualité : on prend une tour en cédant une pièce mineure
    if net == 2 and chess.ROOK in won and any(t in lost for t in minors):
        return "la qualité"
    table = {1: "un pion", 2: "deux pions", 3: "une pièce", 4: "une pièce et un pion",
             5: "une tour", 6: "une tour et un pion", 9: "la dame"}
    return table.get(net, f"environ {net} points de matériel")


def _threat_after(board: chess.Board, first_uci: str):
    """Menace créée par un coup tranquille (via coup nul : si l'adversaire passait)."""
    b = board.copy()
    b.push_uci(first_uci)
    if b.is_check():
        return None
    try:
        b.push(chess.Move.null())
    except Exception:
        return None
    # mat en 1 ?
    for m in b.legal_moves:
        b.push(m)
        mate = b.is_checkmate()
        b.pop()
        if mate:
            return "le mat"
    # gain d'une pièce non défendue (>=3) ?
    me = b.turn
    best = None
    for m in b.legal_moves:
        if b.is_capture(m) and not b.is_en_passant(m):
            tp = b.piece_at(m.to_square)
            if tp and tp.color != me and PIECE_VALUE[tp.piece_type] >= 3:
                if not b.attackers(not me, m.to_square):  # cible non défendue
                    if best is None or PIECE_VALUE[tp.piece_type] > best[0]:
                        best = (PIECE_VALUE[tp.piece_type], tp.piece_type, m.to_square)
    if best:
        return f"de gagner {_art(best[1])} en {_name(best[2])}"
    return None


# --------------------------------------------------------------------------- #
#  Construction des 4 indices                                                  #
# --------------------------------------------------------------------------- #
def _move_sentence(ply: dict, board_before: chess.Board, move: chess.Move) -> str:
    """Phrase d'explication d'un demi-coup (déjà en notation FR dans ply['san'])."""
    san = ply["san"]
    if ply["me"]:
        if ply["mate"]:
            return f"{san} — échec et mat."
        if ply.get("interpose"):
            return f"{san} — intercepte l'échec (et la pièce sera reprise avec gain)."
        if ply.get("sacrifice"):
            return f"{san} — sacrifice : tu donnes du matériel pour forcer la suite."
        if ply["capture"]:
            ct = ply["cap_type"]
            cap = _art(ct) if ct else "une pièce"
            defended = bool(board_before.attackers(not board_before.turn, move.to_square))
            qual = "" if (defended or not ct) else f" (non {_accord(ct, 'défendu')})"
            chk = "avec échec, " if ply["check"] else ""
            return f"{san} — {chk}prend {cap} en {ply['to']}{qual}."
        if ply["check"]:
            return f"{san} — échec : le roi adverse doit réagir."
        return f"{san} — coup tranquille."
    else:
        if ply.get("forced"):
            if ply.get("in_check"):
                return f"{san} — forcé : seule parade à l'échec."
            return f"{san} — forcé (seul coup légal)."
        if ply["capture"]:
            return f"{san} — l'adversaire reprend."
        return f"{san} — l'adversaire réplique."


def _key_signal(board: chess.Board, sol_uci: List[str], ann: dict) -> str:
    """Décrit ce que fait le PREMIER coup de la solution (indice 2, sans vrac)."""
    me = board.turn
    m0 = chess.Move.from_uci(sol_uci[0])
    to = m0.to_square
    gives_check = board.gives_check(m0)
    is_cap = board.is_capture(m0)
    if is_cap:
        if board.is_en_passant(m0):
            cap_type = chess.PAWN
        else:
            tp = board.piece_at(to)
            cap_type = tp.piece_type if tp else None
    else:
        cap_type = None

    # Cas mat : la faiblesse, c'est le roi adverse.
    if ann["outcome"] == "mate":
        ks = [s for s in sd.detect_king_safety(board)
              if s.type in ("king_box", "back_rank")]
        if ks:
            return ks[0].short
        ksq = board.king(not me)
        return (f"Le roi adverse en {_name(ksq)} manque de cases : "
                f"l'échec en {_name(to)} l'enferme.")

    # On joue le coup et on regarde ce que la pièce attaque.
    b = board.copy()
    b.push(m0)
    mover = b.piece_at(to)
    targets = []
    if mover:
        for tsq in b.attacks(to):
            p = b.piece_at(tsq)
            if p and p.color != me and (
                    p.piece_type == chess.KING or PIECE_VALUE[p.piece_type] >= 3):
                targets.append((tsq, p.piece_type))
    enemy = [(s, t) for s, t in targets if t != chess.KING]

    mpt = mover.piece_type if mover else chess.PAWN
    mover_fr = PIECE_FR[mpt]
    is_knight = mpt == chess.KNIGHT
    if gives_check and enemy:
        s, t = max(enemy, key=lambda x: PIECE_VALUE[x[1]])
        nom = " : c'est une fourchette" if is_knight else " (double attaque)"
        return (f"{_poss(mpt).capitalize()} {mover_fr} en {_name(to)} fait échec ET "
                f"attaque {_art(t)} en {_name(s)} en même temps{nom}.")
    if not gives_check and len(enemy) >= 2:
        names = " et ".join(f"{_art(t)} en {_name(s)}" for s, t in enemy[:2])
        nom = "fourchette" if is_knight else "double attaque"
        return (f"{_poss(mpt).capitalize()} {mover_fr} en {_name(to)} attaque en même "
                f"temps {names} ({nom}).")
    if ann["plies"] and ann["plies"][0].get("sacrifice"):
        return (f"Le coup en {_name(to)} est un sacrifice : il détourne une défense "
                f"ou ouvre une ligne vers une cible plus importante.")
    if is_cap and cap_type:
        defended = bool(board.attackers(not me, to))
        if not defended:
            return (f"{_art(cap_type).capitalize()} en {_name(to)} n'est pas "
                    f"{_accord(cap_type, 'défendu')} : tu {_pron(cap_type)} gagnes "
                    f"directement.")
        return f"La prise en {_name(to)} ouvre une suite forcée à ton avantage."
    if ann["threat"]:
        return (f"Le 1er coup ({_name(m0.from_square)}–{_name(to)}) est tranquille "
                f"mais menace {ann['threat']}.")
    return (f"Le coup-clé arrive en {_name(to)} et déclenche une suite forcée "
            f"gagnante.")


def line_notes(board: chess.Board, sol_uci: List[str]) -> List[str]:
    """Une phrase d'explication par demi-coup de la ligne (notation FR)."""
    if not sol_uci:
        return []
    ann = annotate(board, sol_uci)
    b = board.copy()
    notes = []
    for i, ply in enumerate(ann["plies"]):
        mv = chess.Move.from_uci(sol_uci[i])
        notes.append(_move_sentence(ply, b, mv))
        b.push(mv)
    # bilan de l'échange ajouté au dernier coup du solveur (sauf si c'est un mat)
    if ann.get("result") and ann["outcome"] != "mate":
        for i in range(len(ann["plies"]) - 1, -1, -1):
            if ann["plies"][i]["me"]:
                notes[i] += f" Bilan : tu gagnes {ann['result']}."
                break
    return notes


def build_hints(board: chess.Board, sol_uci: List[str], themes: str,
                target_elo: int, signals=None) -> List[str]:
    """4 indices progressifs, centrés sur la solution."""
    if not sol_uci:
        return ["Position sans solution.", "", "", ""]
    if signals is None:
        signals = sd.detect_all(board)
    ann = annotate(board, sol_uci)
    theme_list = (themes or "").split()
    mate_in = next((t for t in theme_list if t.startswith("mateIn")), None)

    # ---- Indice 1 : orientation (ne révèle pas la case) ----
    if ann["outcome"] == "mate":
        n = mate_in[6:] if mate_in else str(ann["n_solver_moves"])
        h1 = (f"Tu peux forcer le mat (en {n}). Cherche une séquence de coups "
              f"forçants — échecs et menaces — qui prive le roi adverse de cases.")
    elif ann["outcome"] == "win_material":
        h1 = ("Il y a du matériel à gagner : une pièce adverse est vulnérable. "
              "Commence par les coups forçants (échecs, captures, menaces).")
    else:
        h1 = ("Le bon plan passe par un coup forçant. Examine d'abord tes échecs "
              "et tes captures avant les coups tranquilles.")

    # ---- Indice 2 : ce que fait le 1er coup de la solution (sans vrac) ----
    h2 = _key_signal(board, sol_uci, ann)

    # ---- Indice 3 : motif + case-clé (sans donner le coup) ----
    key_sq = _name(chess.Move.from_uci(sol_uci[0]).to_square)
    from . import coach  # import tardif (évite le cycle) pour la traduction FR
    motif = None
    for t in _TACTIC_ORDER:
        if t in theme_list:
            motif = coach.THEME_FR.get(t)
            break
    if ann["outcome"] == "mate":
        h3 = f"La case-clé est {key_sq} : un coup forçant y resserre le filet de mat."
    elif motif:
        h3 = f"Motif à trouver : {motif.lower()}. La case-clé est {key_sq}."
    else:
        h3 = f"Concentre-toi sur la case {key_sq} : quel coup forçant peux-tu y jouer ?"

    # ---- Indice 4 : la solution expliquée, coup par coup ----
    sentences = []
    b = board.copy()
    for ply in ann["plies"]:
        mv = chess.Move.from_uci(sol_uci[ply["i"]])
        sentences.append(_move_sentence(ply, b, mv))
        b.push(mv)
    if ann["outcome"] != "mate" and ann.get("result"):
        sentences.append(f"Bilan : tu gagnes {ann['result']}.")
    h4 = "Solution. " + " ".join(sentences)

    # Petite adaptation au niveau : un mot d'encouragement pour les débutants.
    if target_elo and target_elo < 1100:
        h1 = "Pas de panique, procède par étapes. " + h1

    return [h1, h2, h3, h4]
