"""
Moteur de tournoi : génération, gestion des phases, sauvegarde JSON.
Formats supportés :
  - round_robin  : chaque joueur affronte tout le monde une fois
  - chapeau      : 3 chapeaux par niveau, chaque joueur fait 3 matchs
                   (1 contre chaque chapeau), classement global, top N en KO
  - double_elim  : double élimination (winners + losers bracket)

Structure knockout unifiée : toujours ko["rounds"] (liste de listes de matchs)
"""

import json
import os
import uuid
import itertools
import math
from datetime import datetime
from typing import Optional

TOURNAMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "tournaments")


# ─── Persistence ─────────────────────────────────────────────────────────────

def ensure_dir():
    os.makedirs(TOURNAMENTS_DIR, exist_ok=True)


def list_tournaments() -> list[dict]:
    ensure_dir()
    tournaments = []
    for fname in sorted(os.listdir(TOURNAMENTS_DIR), reverse=True):
        if fname.endswith(".json"):
            path = os.path.join(TOURNAMENTS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tournaments.append({
                    "id": data["id"],
                    "name": data["name"],
                    "format": data["format"],
                    "status": data["status"],
                    "created_at": data["created_at"],
                    "players_count": len(data["players"]),
                    "mmr_mode": data.get("mmr_mode", "none"),
                })
            except Exception:
                pass
    return tournaments


def load_tournament(tournament_id: str) -> Optional[dict]:
    ensure_dir()
    path = os.path.join(TOURNAMENTS_DIR, f"{tournament_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tournament(tournament: dict):
    ensure_dir()
    path = os.path.join(TOURNAMENTS_DIR, f"{tournament['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tournament, f, ensure_ascii=False, indent=2)


def delete_tournament(tournament_id: str) -> bool:
    path = os.path.join(TOURNAMENTS_DIR, f"{tournament_id}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


# ─── Création ────────────────────────────────────────────────────────────────

def create_tournament(name: str, fmt: str, players: list[dict],
                      bo: int = 3, mmr_mode: str = "none") -> dict:
    """
    Crée un tournoi et génère la structure complète.

    Parameters
    ----------
    name     : nom du tournoi
    fmt      : "round_robin" | "chapeau" | "double_elim" | "custom"
    players  : liste de dicts {"name": str, "mmr": float}
    bo       : best-of (3, 5 ou 7)
    mmr_mode : "none" | "sets_only" | "sets_upset"
    """
    tid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    tournament = {
        "id": tid,
        "name": name,
        "format": fmt,
        "bo": bo,
        "mmr_mode": mmr_mode,
        "status": "in_progress",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "players": [{"name": p["name"], "mmr": p["mmr"]} for p in players],
        "phase": "group",
        "groups": None,
        "knockout": None,
    }

    if fmt == "round_robin":
        tournament["groups"] = _build_round_robin(players)

    elif fmt == "chapeau":
        tournament["groups"] = _build_chapeau_groups(players)

    elif fmt == "double_elim":
        tournament["knockout"] = _build_double_elim_bracket(players)
        tournament["phase"] = "knockout"

    elif fmt == "custom":
        tournament["custom_matches"] = []
        tournament["phase"] = "custom"

    save_tournament(tournament)
    return tournament


# ─── Round Robin ─────────────────────────────────────────────────────────────

def _build_round_robin(players: list[dict]) -> list[dict]:
    matches = _generate_matches(players)
    return [{
        "id": "G1",
        "name": "Poule unique",
        "players": [p["name"] for p in players],
        "matches": matches,
        "standings": [],
    }]


# ─── Format Chapeau ──────────────────────────────────────────────────────────
#
# Règle : chaque joueur joue exactement 3 matchs — un contre un adversaire
# de chaque chapeau (y compris le sien). On crée donc des groupes de 3
# (un joueur par chapeau). Le classement est GLOBAL sur tous les joueurs.

def _build_chapeau_groups(players: list[dict]) -> list[dict]:
    """
    Tri décroissant par MMR → 3 chapeaux de taille égale (reste → chapeau 3).
    Chaque groupe = 1 joueur par chapeau → 3 matchs par joueur.
    """
    sorted_p = sorted(players, key=lambda p: p["mmr"], reverse=True)
    n = len(sorted_p)
    third = n // 3  # taille de chaque chapeau (on arrondit vers le bas)

    hat1 = sorted_p[:third]
    hat2 = sorted_p[third: 2 * third]
    hat3 = sorted_p[2 * third:]        # peut être plus long si n % 3 != 0

    # On génère autant de groupes que la taille du plus petit chapeau
    num_groups = third
    groups = []

    for i in range(num_groups):
        # Pioche circulaire dans hat3 au cas où il est plus grand
        h3_player = hat3[i % len(hat3)]
        group_players = [hat1[i], hat2[i], h3_player]

        groups.append({
            "id": f"G{i + 1}",
            "name": f"Poule {i + 1}",
            "hat_info": [
                {"hat": 1, "player": hat1[i]["name"]},
                {"hat": 2, "player": hat2[i]["name"]},
                {"hat": 3, "player": h3_player["name"]},
            ],
            "players": [p["name"] for p in group_players],
            "matches": _generate_matches(group_players),
            "standings": [],
        })

    return groups


def compute_global_chapeau_standings(tournament: dict) -> list[dict]:
    """
    Classement global agrégé sur toutes les poules (pour le format chapeau).
    """
    all_players = [p["name"] for p in tournament["players"]]
    stats = {
        p: {"player": p, "wins": 0, "losses": 0,
            "sets_won": 0, "sets_lost": 0, "played": 0}
        for p in all_players
    }

    for group in (tournament.get("groups") or []):
        for m in group["matches"]:
            if not m["played"]:
                continue
            w = m["winner"]
            l = m["p2"] if w == m["p1"] else m["p1"]
            sw = m["score_p1"] if w == m["p1"] else m["score_p2"]
            sl = m["score_p2"] if w == m["p1"] else m["score_p1"]

            if w in stats:
                stats[w]["wins"] += 1
                stats[w]["sets_won"] += sw or 0
                stats[w]["sets_lost"] += sl or 0
                stats[w]["played"] += 1
            if l in stats:
                stats[l]["losses"] += 1
                stats[l]["sets_won"] += sl or 0
                stats[l]["sets_lost"] += sw or 0
                stats[l]["played"] += 1

    standings = sorted(
        stats.values(),
        key=lambda s: (-s["wins"], -(s["sets_won"] - s["sets_lost"]), -s["sets_won"])
    )
    for i, s in enumerate(standings):
        s["rank"] = i + 1
    return standings


# ─── Helpers matchs ──────────────────────────────────────────────────────────

def _generate_matches(players: list[dict]) -> list[dict]:
    matches = []
    for p1, p2 in itertools.combinations(players, 2):
        n1 = p1["name"] if isinstance(p1, dict) else p1
        n2 = p2["name"] if isinstance(p2, dict) else p2
        matches.append({
            "id": uuid.uuid4().hex[:8],
            "p1": n1,
            "p2": n2,
            "winner": None,
            "score_p1": None,
            "score_p2": None,
            "played": False,
            "sets_detail":"",
        })
    return matches

def add_custom_match(tournament: dict, p1: str ,p2: str ,bo: int)->dict:
    #Ajoute un match libre dans un tournoi custom
    match = {
        "id": uuid.uuid4().hex[:8],
        "p1": p1,
        "p2": p2,
        "bo": bo,
        "winner": None,
        "score_p1": None,
        "score_p2": None,
        "played": False,
        "sets_detail":"",
    }
    tournament.setdefault("custom_matches", []).append(match)
    save_tournament(tournament)
    return match

# ─── Double Élimination ──────────────────────────────────────────────────────

def _build_double_elim_bracket(players: list[dict]) -> dict:
    """
    Structure unifiée : ko["rounds"] = liste de rounds du winners bracket.
    Les losers bracket et grande finale sont gérés séparément.
    """
    seeded = sorted(players, key=lambda p: p["mmr"], reverse=True)
    n = len(seeded)

    size = 1
    while size < n:
        size *= 2

    slots = [p["name"] for p in seeded] + [None] * (size - n)
    paired = [(slots[i], slots[size - 1 - i]) for i in range(size // 2)]

    wb_r1 = []
    for i, (p1, p2) in enumerate(paired):
        m = {
            "id": uuid.uuid4().hex[:8],
            "round_name": get_round_name(size, 1),
            "position": i,
            "bracket": "winners",
            "p1": p1,
            "p2": p2,
            "winner": None,
            "loser": None,
            "score_p1": None,
            "score_p2": None,
            "played": False,
            "sets_detail":"",
        }
        if p1 is None:
            m.update(winner=p2, loser=None, played=True)
        elif p2 is None:
            m.update(winner=p1, loser=None, played=True)
        wb_r1.append(m)

    return {
        "size": size,
        "current_round": 1,
        "rounds": [wb_r1],          # ← structure unifiée avec les autres formats
        "losers_rounds": [],
        "grand_final": None,
        "champion": None,
        "standings": [],
        "qualified": [p["name"] for p in seeded],
    }


# ─── Classements de poule (round-robin / chapeau par poule) ──────────────────

def compute_group_standings(group: dict) -> list[dict]:
    stats = {p: {"player": p, "wins": 0, "losses": 0,
                 "sets_won": 0, "sets_lost": 0, "played": 0}
             for p in group["players"]}

    for m in group["matches"]:
        if not m["played"]:
            continue
        w = m["winner"]
        l = m["p2"] if w == m["p1"] else m["p1"]
        sw = m["score_p1"] if w == m["p1"] else m["score_p2"]
        sl = m["score_p2"] if w == m["p1"] else m["score_p1"]

        if w and w in stats:
            stats[w]["wins"] += 1
            stats[w]["sets_won"] += sw or 0
            stats[w]["sets_lost"] += sl or 0
            stats[w]["played"] += 1
        if l and l in stats:
            stats[l]["losses"] += 1
            stats[l]["sets_won"] += sl or 0
            stats[l]["sets_lost"] += sw or 0
            stats[l]["played"] += 1

    standings = sorted(
        stats.values(),
        key=lambda s: (-s["wins"], -(s["sets_won"] - s["sets_lost"]), -s["sets_won"])
    )
    for i, s in enumerate(standings):
        s["rank"] = i + 1
    return standings


def get_group_completion(group: dict) -> tuple[int, int]:
    played = sum(1 for m in group["matches"] if m["played"])
    return played, len(group["matches"])


def all_groups_complete(tournament: dict) -> bool:
    if not tournament.get("groups"):
        return True
    return all(get_group_completion(g)[0] == get_group_completion(g)[1]
               for g in tournament["groups"])


# ─── Génération du tableau KO depuis les poules ──────────────────────────────

def generate_knockout_from_groups(tournament: dict, top_n: int = 8) -> dict:
    fmt = tournament["format"]

    if fmt == "chapeau":
        all_standings = compute_global_chapeau_standings(tournament)
    else:
        # round_robin : classement de la poule unique
        all_standings = compute_group_standings(tournament["groups"][0])

    qualified_stats = all_standings[:top_n]
    qualified_names = [s["player"] for s in qualified_stats]

    # Têtes de série : meilleurs en tête
    seeded = qualified_names[:]

    size = top_n
    paired = [(seeded[i], seeded[size - 1 - i]) for i in range(size // 2)]

    matches = []
    for i, (p1, p2) in enumerate(paired):
        matches.append({
            "id": uuid.uuid4().hex[:8],
            "round_name": get_round_name(size, 1),
            "position": i,
            "bracket": "winners",
            "p1": p1,
            "p2": p2,
            "winner": None,
            "loser": None,
            "score_p1": None,
            "score_p2": None,
            "played": False,
            "sets_detail":"",
        })

    ko = {
        "size": size,
        "qualified": seeded,
        "current_round": 1,
        "rounds": [matches],
        "grand_final": None,
        "champion": None,
        "standings": [],
    }

    tournament["knockout"] = ko
    tournament["phase"] = "knockout"
    save_tournament(tournament)
    return ko


def get_round_name(size: int, round_num: int) -> str:
    remaining = size // (2 ** (round_num - 1))
    if remaining == 2:
        return "Finale"
    if remaining == 4:
        return "Demi-finales"
    if remaining == 8:
        return "Quarts de finale"
    if remaining == 16:
        return "Huitièmes de finale"
    return f"Tour {round_num}"


def advance_knockout_round(tournament: dict) -> bool:
    ko = tournament["knockout"]
    current_matches = ko["rounds"][-1]

    if not all(m["played"] for m in current_matches):
        return False

    winners = [m["winner"] for m in current_matches if m["winner"]]

    if len(winners) == 1:
        ko["champion"] = winners[0]
        tournament["phase"] = "done"
        tournament["status"] = "finished"
        save_tournament(tournament)
        return False

    round_num = len(ko["rounds"]) + 1
    new_matches = []
    for i in range(0, len(winners), 2):
        if i + 1 < len(winners):
            new_matches.append({
                "id": uuid.uuid4().hex[:8],
                "round_name": get_round_name(ko["size"], round_num),
                "position": i // 2,
                "bracket": "winners",
                "p1": winners[i],
                "p2": winners[i + 1],
                "winner": None,
                "loser": None,
                "score_p1": None,
                "score_p2": None,
                "played": False,
            })

    ko["rounds"].append(new_matches)
    ko["current_round"] = round_num
    save_tournament(tournament)
    return True


# ─── Enregistrement résultats ────────────────────────────────────────────────

def record_group_match(tournament: dict, group_id: str, match_id: str, winner: str, score_p1: int, score_p2: int, sets_detail: str) -> bool:
    for group in (tournament.get("groups") or []):
        if group["id"] == group_id:
            for m in group["matches"]:
                if m["id"] == match_id:
                    m["winner"] = winner
                    m["score_p1"] = score_p1
                    m["score_p2"] = score_p2
                    m["played"] = True
                    m["sets_detail"] = sets_detail
                    group["standings"] = compute_group_standings(group)
                    save_tournament(tournament)
                    return True
    return False


def record_knockout_match(tournament: dict, match_id: str,
                          winner: str, score_p1: int, score_p2: int, sets_detail: str) -> bool:
    ko = tournament["knockout"]
    for round_matches in ko["rounds"]:
        for m in round_matches:
            if m["id"] == match_id:
                loser = m["p2"] if winner == m["p1"] else m["p1"]
                m["winner"] = winner
                m["loser"] = loser
                m["score_p1"] = score_p1
                m["score_p2"] = score_p2
                m["played"] = True
                m["sets_detail"] = sets_detail
                save_tournament(tournament)
                if all(x["played"] for x in round_matches):
                    advance_knockout_round(tournament)
                return True
    return False

def record_custom_match(tournament: dict, match_id: str, winner: str, score_p1: int, score_p2: int, sets_detail:str) -> bool:
    """Enregistre le résultat d'un match custom."""
    for m in tournament.get("custom_matches", []):
        if m["id"] == match_id:
            m["winner"] = winner
            m["score_p1"] = score_p1
            m["score_p2"] = score_p2
            m["played"] = True
            m["sets_detail"] = sets_detail
            save_tournament(tournament)
            return True
    return False


# ─── Calcul MMR pour l'enregistrement post-tournoi ──────────────────────────

def compute_mmr_delta(winner_mmr: float, loser_mmr: float,
                      score_w: int, score_l: int, mmr_mode: str) -> tuple[int, int]:
    """
    Retourne (delta_winner, delta_loser) selon le mode MMR choisi.

    Modes :
      none        → (0, 0)  pas d'impact
      sets_only   → différence de sets uniquement (comme le mode normal de l'app)
      sets_upset  → différence de sets + bonus upset si le moins bien classé gagne
    """
    if mmr_mode == "none":
        return 0, 0

    diff = score_w - score_l  # toujours positif

    if mmr_mode == "sets_only":
        return diff, -diff

    if mmr_mode == "sets_upset":
        if winner_mmr < loser_mmr:
            rank_diff = int(abs(loser_mmr - winner_mmr))
            bonus = max(1, rank_diff // 3)
            return diff + bonus, -(diff + bonus)
        return diff, -diff

    return 0, 0
