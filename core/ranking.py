"""
Logique centrale : joueurs, calcul Elo, sauvegarde des données.
"""

import json
import base64
import requests
import streamlit as st
import os
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "players.json")
DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")

# ─── Nommage des fichiers spéciaux ───────────────────────────────────────────

def _backup_path() -> str:
    """Retourne le chemin du backup quotidien (players_YYYY-MM-DD.json)."""
    files = _list_backup_files()
    return files[0] if files else None

def _export_path() -> str:
    """Retourne le chemin du backup quotidien (players_YYYY-MM-DD.json)."""
    files = _list_export_files()
    return files[0] if files else None

def _list_backup_files() -> list[str]:
    """Liste tous les backups datés, du plus récent au plus ancien."""
    import glob
    pattern = os.path.join(DATA_DIR, "players_????-??-??.json")
    files = glob.glob(pattern)
    return sorted(files, reverse=True)

def _list_export_files() -> list[str]:
    """Liste tous les exports datés, du plus récent au plus ancien."""
    import glob
    pattern = os.path.join(DATA_DIR, "export_????-??-??.json")
    files = glob.glob(pattern)
    return sorted(files, reverse=True)

def maybe_create_daily_backup():
    """
    Crée ou met à jour le backup quotidien si nécessaire.
    Appelée au premier chargement de l'app chaque jour.
    Règle : on garde exactement 1 fichier backup (players_DATE.json).
    Si le backup existant date d'hier ou avant → on le renomme à aujourd'hui
    et on écrase son contenu avec players.json actuel.
    """
    if not os.path.exists(DATA_FILE):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    today_backup = os.path.join(DATA_DIR, f"players_{today}.json")

    existing_backups = _list_backup_files()

    # Supprimer les vieux backups sauf le plus récent
    for old in existing_backups[1:]:
        os.remove(old)

    # Si le backup du jour existe déjà → rien à faire
    if os.path.exists(today_backup):
        return

    # Supprimer l'ancien backup s'il existe
    if existing_backups:
        os.remove(existing_backups[0])

    # Créer le backup du jour
    import shutil
    shutil.copy2(DATA_FILE, today_backup)

def display_mmr(value: float) -> int:
    return int(round(value))

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"players": [], "matches": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    
data = load_data()

def calculate_elo_change(winner_mmr: int, loser_mmr: int, sets_w: int, sets_l: int) -> int:
    """
    Calcule le changement de MMR selon les règles :
    1. Différence de sets
    2. Copie du MMR si le vainqueur était moins bien classé
    """
    diff = sets_w - sets_l

    # Cas où le vainqueur était moins bien classé
    if winner_mmr < loser_mmr:
        return (loser_mmr - winner_mmr) + diff

    # Cas normal
    return diff

def save_data(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_ranks(data: dict):
    players_sorted = [p for p in data["players"] if p.get("status")== "active"]
    players_sorted = sorted(players_sorted, key=lambda p: p["mmr"], reverse=True)
    for i, p in enumerate(players_sorted, start=1):
        p["rank"] = i
        if i < p["best_rank"]:
            p["best_rank"]=i
        if(p["mmr"]>p["best_mmr"]):
            p["best_mmr"]

            
# ─── Lecture ─────────────────────────────────────────────────────────────────

def get_players(data: dict) -> list:
    classement = [p for p in data["players"] if p.get("status")== "active"]
    return sorted(classement, key=lambda p: p["mmr"], reverse=True)

def get_everyone(data: dict) -> list:
    return sorted(data["players"],key=lambda p: p["mmr"],reverse=True)

def get_retired_players(data: dict | None = None) -> list:
    return [p for p in data["players"] if p.get("status") == "retired"]

def get_matches(data: dict) -> list:
    """
    Retourne la liste des matchs enregistrés.
    """
    return sorted(data["matches"], key=lambda m: m["date"], reverse=True)


def add_player(data: dict, name: str, mmr: int = 100) -> dict:
    for p in data["players"]:
        if p["name"].lower() == name.lower():
            raise ValueError(f"Le joueur « {name} » existe déjà.")
    player = {
        "id": _next_id(data),
        "name": name,
        "mmr": mmr,
        "best_mmr":0,
        "wins": 0,
        "losses": 0,
        "rank": _next_id(data),
        "best_rank": _next_id(data),
        "status": "active",
        "absences":0,
        "history": [{"date": datetime.now().strftime("%Y-%m-%d"), "mmr": mmr}],
    }
    data["players"].append(player)
    update_ranks(data)
    save_data(data)
    return player

def retire_player(name: str) -> tuple[bool, str]:
    data = load_data()
    player = next((p for p in data["players"] if p["name"] == name), None)
    if not player:
        return False, "Joueur introuvable."
    if player.get("status") == "retired":
        return False, f"{name} est déjà retraité."
    player["status"] = "retired"
    player["retired_date"] = datetime.now().strftime("%Y-%m-%d")
    update_ranks(data)
    save_data(data)
    return True, f"{name} est maintenant retraité. Son historique est conservé."

def reactivate_player(name: str, new_mmr: int = 1000) -> tuple[bool, str]:
    data = load_data()
    player = next((p for p in data["players"] if p["name"] == name), None)
    if not player:
        return False, "Joueur introuvable."
    if player.get("status", "active") == "active":
        return False, f"{name} est déjà actif."
    player["status"] = "active"
    player["mmr"] = new_mmr
    player.pop("retired_date", None)
    today = datetime.now().strftime("%Y-%m-%d")
    player["history"].append({"date": today, "mmr": new_mmr, "note": "réactivation"})
    save_data(data)
    return True, f"{name} réactivé avec {new_mmr} points."

def remove_player(data: dict, player_id: int):
    data["players"] = [p for p in data["players"] if p["id"] != player_id]
    save_data(data)
    return True, "OK"

def get_last_snapshot(player):
    return player["history"][-1]

from datetime import datetime

def add_snapshot(player,mmr_value, match_datetime):
    if player["history"] and player["history"][-1]["date"]==match_datetime:
        player["history"][-1]["mmr"]=mmr_value
        return
    
    player["history"].append({
        "date": match_datetime.split(" ")[0],
        "mmr":mmr_value
    })

def si_nouvelle_snapshot(player, match_datetime):
    last=get_last_snapshot(player)
    current = player["mmr"]

    delta = current-last["mmr"]

    if delta <=-0.5:
        add_snapshot(player,current, match_datetime)

def record_match(data: dict, winner_name: str, loser_name: str, sets_w: int, sets_l: int, sets_detail="", match_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")):
    winner = next((p for p in data["players"] if p["name"] == winner_name), None)
    loser = next((p for p in data["players"] if p["name"] == loser_name), None)

    if winner is None or loser is None:
        return False, "Joueur introuvable."

    diff = sets_w - sets_l

    # Règle 2 : copie du MMR si le vainqueur était moins bien classé
    if winner["mmr"] < loser["mmr"]:
        winner["mmr"] = loser["mmr"] + diff
    else:
        winner["mmr"] += diff
        if(winner["mmr"]>winner["best_mmr"]):
            winner["best_mmr"]=winner["mmr"]

    loser["mmr"]+=sets_l-sets_w

    # Règle 3 : tous les autres joueurs voient leur compteur d'absence augmenter
    total = len([p for p in data["players"] if p.get("status") == "active"])

    for p in data["players"]:
        if p["name"] not in (winner_name, loser_name) and p.get("status") == "active":
            p["mmr"] -= int(p["absences"]/5)*3/total
            p["absences"]+=1
            si_nouvelle_snapshot(p, match_datetime)

    winner["absences"]=0
    loser["absences"]=0

    # Historique
    winner["history"].append({"date": match_datetime.split(" ")[0], "mmr": winner["mmr"]})
    winner["wins"]+=1
    loser["losses"]+=1
    loser["history"].append({"date": match_datetime.split(" ")[0], "mmr": loser["mmr"]})

    # Enregistrement du match
    match_record = {
        "date": match_datetime,
        "winner": winner_name,
        "loser": loser_name,
        "score": f"{sets_w}-{sets_l}",
        "sets_detail":sets_detail,
        "delta": diff,
        "winner_mmr_after": winner["mmr"],
        "loser_mmr_after": loser["mmr"],
        "rank_winner":winner["rank"],
        "rank_loser":loser["rank"],
    }
    data["matches"].append(match_record)
    update_ranks(data)
    save_data(data)
    return True, "OK"

def get_rank_evolution(data: dict) -> dict:
    """
    Compare le classement actuel avec le dernier backup automatique.
    Retourne un dict {nom: delta} où delta > 0 = montée, < 0 = descente, 0 = stable.
    """
    backup = _backup_path()
    if not backup or not os.path.exists(backup):
        return {}

    with open(backup, "r", encoding="utf-8") as f:
        old_data = json.load(f)

    # On lit directement le champ "rank" sauvegardé dans le backup
    old_ranks = {
        p["name"]: p["rank"]
        for p in old_data["players"]
        if p.get("status") == "active" and "rank" in p
    }

    evolution = {}
    for p in data["players"]:
        if p.get("status") != "active":
            continue
        name = p["name"]
        if name in old_ranks:
            # old_rank - current_rank : positif = montée (ex : 5→3 = +2)
            evolution[name] = old_ranks[name] - p["rank"]

    return evolution


def _elo_delta(winner_mmr: int, loser_mmr: int, k: int = 32) -> int:
    expected = 1 / (1 + 10 ** ((loser_mmr - winner_mmr) / 400))
    return max(1, round(k * (1 - expected)))


def _get_player_by_id(data: dict, player_id: int):
    for p in data["players"]:
        if p["id"] == player_id:
            return p
    return None




def _next_id(data: dict) -> int:
    if not data["players"]:
        return 1
    return max(p["id"] for p in data["players"]) + 1


# ─── Export ──────────────────────────────────────────────────────────────────

def create_export() -> tuple[bool, str]:
    """
    Crée un fichier export_YYYY-MM-DD.json dans data/.
    Supprime les anciens exports (on garde le dernier uniquement).
    Retourne (succès, chemin du fichier créé).
    """
    import shutil

    if not os.path.exists(DATA_FILE):
        return False, "Aucun fichier de données trouvé."

    # Supprimer les anciens exports
    for old in _list_export_files():
        os.remove(old)

    today = datetime.now().strftime("%Y-%m-%d")
    export_path = os.path.join(DATA_DIR, f"export_{today}.json")
    shutil.copy2(DATA_FILE, export_path)
    return True, export_path


def get_export_json_bytes() -> bytes | None:
    """Retourne le contenu de players.json en bytes pour st.download_button."""
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, "rb") as f:
        return f.read()


# ─── Chargement d'une version antérieure ─────────────────────────────────────

def load_version(source_path: str) -> tuple[bool, str]:
    """
    Remplace players.json par le fichier source_path.
    Crée un backup du fichier courant avant d'écraser.
    """
    import shutil

    if not os.path.exists(source_path):
        return False, "Fichier introuvable."

    # Backup de sécurité du fichier courant avant écrasement
    today = datetime.now().strftime("%Y-%m-%d")
    safety = os.path.join(DATA_DIR, f"players_{today}.json")
    if os.path.exists(DATA_FILE) and not os.path.exists(safety):
        shutil.copy2(DATA_FILE, safety)

    shutil.copy2(source_path, DATA_FILE)
    return True, "Données restaurées avec succès."


def describe_version_file(path: str) -> str:
    """
    Retourne un libellé lisible pour un fichier de backup ou d'export.
    """
    filename = os.path.basename(path)

    if filename.startswith("players_") and filename.endswith(".json"):
        date_str = filename[len("players_"):-len(".json")]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            today = datetime.now().date()
            delta = (today - d.date()).days
            if delta == 0:
                label = "aujourd'hui"
            elif delta == 1:
                label = "hier"
            else:
                label = f"il y a {delta} jours"
            return f"Sauvegarde du {d.strftime('%d/%m/%Y')} ({label})"
        except ValueError:
            return filename

    if filename.startswith("export_") and filename.endswith(".json"):
        date_str = filename[len("export_"):-len(".json")]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return f"Dernier export — {d.strftime('%d/%m/%Y')}"
        except ValueError:
            return filename

    return filename


def list_available_versions() -> list[dict]:
    """
    Retourne la liste des versions disponibles (backup + exports),
    chacune sous forme {"path": ..., "label": ..., "type": "backup"|"export"}.
    """
    versions = []
    for p in _list_backup_files():
        versions.append({"path": p, "label": describe_version_file(p), "type": "backup"})
    for p in _list_export_files():
        versions.append({"path": p, "label": describe_version_file(p), "type": "export"})
    return versions


# ─── Resimulation ────────────────────────────────────────────────────────────
# Versions in-memory de add_player et record_match : logique identique,
# mais SANS appel à save_data() — utilisées exclusivement par resimulate().

def _add_player_in_memory(data: dict, name: str, mmr: int = 100, history_date: str = None) -> dict:
    """Ajoute un joueur dans data sans écrire sur le disque."""
    for p in data["players"]:
        if p["name"].lower() == name.lower():
            raise ValueError(f"Le joueur « {name} » existe déjà.")
    date = history_date or datetime.now().strftime("%Y-%m-%d")
    player = {
        "id": _next_id(data),
        "name": name,
        "mmr": mmr,
        "best_mmr": mmr,
        "wins": 0,
        "losses": 0,
        "rank": _next_id(data),
        "best_rank": _next_id(data),
        "status": "active",
        "absences":0,
        "history": [{"date": date, "mmr": mmr}],
    }
    data["players"].append(player)
    update_ranks(data)
    return player


def _record_match_in_memory(data: dict, winner_name: str, loser_name: str,
                             sets_w: int, sets_l: int, sets_detail: str = "",
                             match_datetime: str = None) -> tuple[bool, str]:
    """Enregistre un match dans data sans écrire sur le disque."""
    winner = next((p for p in data["players"] if p["name"] == winner_name), None)
    loser  = next((p for p in data["players"] if p["name"] == loser_name),  None)

    if winner is None or loser is None:
        return False, "Joueur introuvable."

    diff = sets_w - sets_l

    if winner["mmr"] < loser["mmr"]:
        winner["mmr"] = loser["mmr"] + diff
    else:
        winner["mmr"] += diff
        if winner["mmr"] > winner["best_mmr"]:
            winner["best_mmr"] = winner["mmr"]

    loser["mmr"] += sets_l - sets_w

    total = len([p for p in data["players"] if p.get("status") == "active"])

    for p in data["players"]:
        if p["name"] not in (winner_name, loser_name) and p.get("status") == "active":
            p["mmr"] -= int(p["absences"]/5)*3/total
            p["absences"]+=1
            si_nouvelle_snapshot(p, match_datetime)

    winner["absences"]=0
    loser["absences"]=0

    match_date = (match_datetime or datetime.now().strftime("%Y-%m-%d %H:%M"))[:10]
    winner["history"].append({"date": match_date, "mmr": winner["mmr"]})
    winner["wins"] += 1
    loser["losses"] += 1
    loser["history"].append({"date": match_date, "mmr": loser["mmr"]})

    match_record = {
        "date": match_datetime or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "winner": winner_name,
        "loser": loser_name,
        "score": f"{sets_w}-{sets_l}",
        "sets_detail": sets_detail,
        "delta": diff,
        "winner_mmr_after": winner["mmr"],
        "loser_mmr_after": loser["mmr"],
        "rank_winner": winner["rank"],
        "rank_loser": loser["rank"],
    }
    data["matches"].append(match_record)
    update_ranks(data)
    return True, "OK"


def resimulate(source_path: str) -> tuple[bool, str, dict | None]:
    """
    Repart de zéro en rejouant tous les événements du fichier source_path
    dans l'ordre chronologique (ajout de joueurs + matchs).

    Retourne (succès, message, nouveau_data ou None).
    N'écrit RIEN sur le disque — c'est apply_resimulation() qui confirme.
    """
    if not os.path.exists(source_path):
        return False, "Fichier source introuvable.", None

    with open(source_path, "r", encoding="utf-8") as f:
        source = json.load(f)

    players_sorted = sorted(
        source["players"],
        key=lambda p: (p["id"], p["history"][0]["date"] if p["history"] else "9999-99-99")
    )
    matches_sorted = sorted(source["matches"], key=lambda m: m["date"])

    events = []
    for p in players_sorted:
        events.append({
            "type": "add_player",
            "date": p["history"][0]["date"] if p["history"] else "1970-01-01",
            "name": p["name"],
            "mmr": p["history"][0]["mmr"] if p["history"] else 1000,
            "status": p.get("status", "active"),
            "retired_date": p.get("retired_date"),
        })
    for m in matches_sorted:
        score_parts = m["score"].split("-")
        events.append({
            "type": "match",
            "date": m["date"],
            "winner": m["winner"],
            "loser": m["loser"],
            "sets_w": int(score_parts[0]),
            "sets_l": int(score_parts[1]),
            "sets_detail": m.get("sets_detail", ""),
        })

    events.sort(key=lambda e: (e["date"], 0 if e["type"] == "add_player" else 1))

    new_data = {"players": [], "matches": []}
    errors = []

    for ev in events:
        if ev["type"] == "add_player":
            try:
                _add_player_in_memory(new_data, ev["name"], ev["mmr"], history_date=ev["date"])
                if ev["status"] == "retired":
                    player = next((p for p in new_data["players"] if p["name"] == ev["name"]), None)
                    if player:
                        player["status"] = "retired"
                        if ev.get("retired_date"):
                            player["retired_date"] = ev["retired_date"]
            except ValueError as e:
                errors.append(str(e))
        elif ev["type"] == "match":
            ok, msg = _record_match_in_memory(
                new_data,
                ev["winner"], ev["loser"],
                ev["sets_w"], ev["sets_l"],
                ev["sets_detail"],
                match_datetime=ev["date"],
            )
            if not ok:
                errors.append(f"Match {ev['winner']} vs {ev['loser']} ({ev['date']}) : {msg}")

    if errors:
        return False, f"Resimulation terminée avec {len(errors)} erreur(s) : " + "; ".join(errors), new_data

    return True, f"Resimulation réussie — {len(players_sorted)} joueurs, {len(matches_sorted)} matchs rejoués.", new_data


def apply_resimulation(new_data: dict) -> tuple[bool, str]:
    """Sauvegarde le résultat d'une resimulation comme nouveau players.json."""
    save_data(new_data)
    return True, "Nouveau classement appliqué."