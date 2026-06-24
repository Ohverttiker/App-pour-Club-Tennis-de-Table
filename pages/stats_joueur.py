"""
Page de statistiques détaillées d'un joueur.
Appelée depuis joueurs.py via st.session_state["selected_player"].
"""

import streamlit as st
import pandas as pd
from collections import defaultdict
from core.ranking import load_data, get_players, display_mmr


# ─── Calcul des stats ────────────────────────────────────────────────────────

def _parse_sets_detail(sets_detail: str) -> list[tuple[int, int]]:
    """Parse '11-8 8-11 11-6' → [(11,8), (8,11), (11,6)]"""
    sets = []
    for s in sets_detail.strip().split():
        parts = s.split("-")
        if len(parts) == 2:
            try:
                sets.append((int(parts[0]), int(parts[1])))
            except ValueError:
                pass
    return sets


def compute_stats(player_name: str, data: dict) -> dict:
    matches = data["matches"]
    all_players = {p["name"]: p for p in data["players"]}
    active_players = {p["name"]: p for p in data["players"] if p.get("status") == "active"}

    # Matchs du joueur
    player_matches = [
        m for m in matches
        if m["winner"] == player_name or m["loser"] == player_name
    ]
    player_matches_sorted = sorted(player_matches, key=lambda m: m["date"])

    # ── Bilan général ────────────────────────────────────────────────────────
    wins = sum(1 for m in player_matches if m["winner"] == player_name)
    losses = sum(1 for m in player_matches if m["loser"] == player_name)
    total = wins + losses
    winrate = (wins / total * 100) if total > 0 else 0.0

    # ── Sets et points ───────────────────────────────────────────────────────
    sets_won = sets_lost = 0
    pts_won = pts_lost = 0

    for m in player_matches:
        is_winner = m["winner"] == player_name
        sets = _parse_sets_detail(m.get("sets_detail", ""))
        for (a, b) in sets:
            if is_winner:
                pts_won += a
                pts_lost += b
            else:
                pts_won += b
                pts_lost += a

        if(is_winner):
            sets_won+=3
            sets_lost+=3-m["delta"]
        else:
            sets_won+=3-m["delta"]
            sets_lost+=3

    total_sets = sets_won + sets_lost
    sets_ratio = (sets_won / total_sets * 100) if total_sets > 0 else 0.0
    total_pts = pts_won + pts_lost
    pts_ratio = (pts_won / total_pts * 100) if total_pts > 0 else 0.0

    # ── Matchs en 5 sets ────────────────────────────────────────────────────
    five_set_matches = [m for m in player_matches if m.get("score", "").split("-")[0] == "3"
                        and m.get("score", "").split("-")[1] == "2"]
    five_set_total = len(five_set_matches)
    five_set_wins = sum(1 for m in five_set_matches if m["winner"] == player_name)
    five_set_losses = five_set_total - five_set_wins
    five_set_ratio_of_all = (five_set_total / total * 100) if total > 0 else 0.0

    # ── Bilan par adversaire ─────────────────────────────────────────────────
    opponent_stats = defaultdict(lambda: {"wins": 0, "losses": 0})
    for m in player_matches:
        if m["winner"] == player_name:
            opponent_stats[m["loser"]]["wins"] += 1
        else:
            opponent_stats[m["winner"]]["losses"] += 1

    def get_rank(name):
        p = active_players.get(name) or all_players.get(name)
        return p["rank"] if p and "rank" in p else 9999

    # ── Pire ennemi (plus de défaites) ──────────────────────────────────────
    pire_ennemi = None
    if any(v["losses"] > 0 for v in opponent_stats.values()):
        max_losses = max(v["losses"] for v in opponent_stats.values())
        candidates = [n for n, v in opponent_stats.items() if v["losses"] == max_losses]
        # En cas d'égalité : joueur le moins bien classé (rang le plus élevé)
        pire_ennemi = max(candidates, key=lambda n: get_rank(n))

    # ── Cible favorite (plus de victoires) ──────────────────────────────────
    cible_favorite = None
    if any(v["wins"] > 0 for v in opponent_stats.values()):
        max_wins = max(v["wins"] for v in opponent_stats.values())
        candidates = [n for n, v in opponent_stats.items() if v["wins"] == max_wins]
        # En cas d'égalité : joueur le mieux classé (rang le plus faible)
        cible_favorite = min(candidates, key=lambda n: get_rank(n))

    # ── Plus grand rival (plus de matchs, excluant pire ennemi et cible) ────
    already_mentioned = set()
    if pire_ennemi:
        already_mentioned.add(pire_ennemi)
    if cible_favorite:
        already_mentioned.add(cible_favorite)

    plus_grand_rival = None
    opponent_totals = {
        n: v["wins"] + v["losses"]
        for n, v in opponent_stats.items()
    }
    if opponent_totals:
        candidates_all = sorted(opponent_totals.items(), key=lambda x: -x[1])
        max_total = candidates_all[0][1]
        top_candidates = [n for n, t in candidates_all if t == max_total]

        # Exclure les déjà mentionnés si possible
        filtered = [n for n in top_candidates if n not in already_mentioned]
        pool = filtered if filtered else top_candidates
        # En cas d'égalité : joueur le mieux classé
        plus_grand_rival = min(pool, key=lambda n: get_rank(n))

    # ── Streak actuelle ──────────────────────────────────────────────────────
    streak_value = 0
    streak_type = None  # "win" ou "loss"
    if player_matches_sorted:
        last_result = "win" if player_matches_sorted[-1]["winner"] == player_name else "loss"
        count = 0
        for m in reversed(player_matches_sorted):
            result = "win" if m["winner"] == player_name else "loss"
            if result == last_result:
                count += 1
            else:
                break
        if count >= 3:
            streak_value = count
            streak_type = last_result

    # ── Perf contre mieux/moins bien classés ────────────────────────────────
    wins_vs_better = losses_vs_better = 0
    wins_vs_weaker = losses_vs_weaker = 0

    for m in player_matches:
        is_winner = m["winner"] == player_name
        rank_self = m["rank_winner"] if is_winner else m["rank_loser"]
        rank_opp = m["rank_loser"] if is_winner else m["rank_winner"]
        vs_better = rank_opp < rank_self  # rang plus faible = mieux classé

        if is_winner:
            if vs_better:
                wins_vs_better += 1
            else:
                wins_vs_weaker += 1
        else:
            if vs_better:
                losses_vs_better += 1
            else:
                losses_vs_weaker += 1

    # ── Historique des matchs (liste) ────────────────────────────────────────
    match_history = []
    for m in reversed(player_matches_sorted):
        is_winner = m["winner"] == player_name
        opponent = m["loser"] if is_winner else m["winner"]
        score_raw = m.get("score", "")

        # Afficher le score du point de vue du joueur
        if is_winner:
            score_display = score_raw
        else:
            parts = score_raw.split("-")
            score_display = f"{parts[1]}-{parts[0]}" if len(parts) == 2 else score_raw

        match_history.append({
            "Date": m["date"][:10],
            "Adversaire": opponent,
            "Résultat": "✅ Victoire" if is_winner else "❌ Défaite",
            "Score": score_display,
            "Sets": m.get("sets_detail", "—"),
        })

    # ── Données pour le graphique MMR ────────────────────────────────────────
    # Retourne les noms des joueurs à tracer (pour le graphique)
    chart_players = [player_name]
    for extra in [plus_grand_rival, pire_ennemi, cible_favorite]:
        if extra and extra not in chart_players:
            chart_players.append(extra)

    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "winrate": winrate,
        "sets_won": sets_won,
        "sets_lost": sets_lost,
        "sets_ratio": sets_ratio,
        "pts_won": pts_won,
        "pts_lost": pts_lost,
        "pts_ratio": pts_ratio,
        "five_set_total": five_set_total,
        "five_set_wins": five_set_wins,
        "five_set_losses": five_set_losses,
        "five_set_ratio_of_all": five_set_ratio_of_all,
        "pire_ennemi": pire_ennemi,
        "cible_favorite": cible_favorite,
        "plus_grand_rival": plus_grand_rival,
        "opponent_stats": dict(opponent_stats),
        "streak_value": streak_value,
        "streak_type": streak_type,
        "wins_vs_better": wins_vs_better,
        "losses_vs_better": losses_vs_better,
        "wins_vs_weaker": wins_vs_weaker,
        "losses_vs_weaker": losses_vs_weaker,
        "match_history": match_history,
        "chart_players": chart_players,
    }


def build_mmr_chart(player_name: str, chart_players: list[str], data: dict, rank1_name: str, rank1_plus1_name: str) -> pd.DataFrame:
    """
    Construit un DataFrame avec l'historique MMR de tous les joueurs à tracer.
    Ajoute automatiquement le n°1 et le joueur juste au-dessus dans le classement.
    """
    all_players = {p["name"]: p for p in data["players"]}

    to_plot = list(dict.fromkeys(chart_players))  # dédoublonne en gardant l'ordre
    for extra in [rank1_name, rank1_plus1_name]:
        if extra and extra not in to_plot:
            to_plot.append(extra)

    # Collecte de tous les points de date
    all_dates = set()
    for name in to_plot:
        p = all_players.get(name)
        if p:
            for h in p.get("history", []):
                all_dates.add(h["date"])

    if not all_dates:
        return pd.DataFrame()

    sorted_dates = sorted(all_dates)

    rows = {}
    for name in to_plot:
        p = all_players.get(name)
        if not p:
            continue
        history = sorted(p.get("history", []), key=lambda h: h["date"])
        # Forward-fill : pour chaque date globale, on prend le dernier MMR connu
        mmr_by_date = {}
        last_mmr = None
        hi = 0
        for date in sorted_dates:
            while hi < len(history) and history[hi]["date"] <= date:
                last_mmr = history[hi]["mmr"]
                hi += 1
            if last_mmr is not None:
                mmr_by_date[date] = round(last_mmr)
        rows[name] = mmr_by_date

    df = pd.DataFrame(rows, index=sorted_dates)
    df.index.name = "Date"
    return df


# ─── Affichage ───────────────────────────────────────────────────────────────

def show(player_name: str):
    data = load_data()
    active_players = get_players(data)
    all_players_map = {p["name"]: p for p in data["players"]}

    player = all_players_map.get(player_name)
    if not player:
        st.error(f"Joueur « {player_name} » introuvable.")
        if st.button("← Retour"):
            st.session_state["selected_player"] = None
            st.rerun()
        return

    # ── Bouton retour ────────────────────────────────────────────────────────
    if st.button("← Retour à la liste des joueurs"):
        st.session_state["selected_player"] = None
        st.rerun()

    st.markdown(f"## 📊 Statistiques — {player_name}")

    stats = compute_stats(player_name, data)

    # ── Streak ──────────────────────────────────────────────────────────────
    if stats["streak_value"] >= 3:
        if stats["streak_type"] == "win":
            st.success(f"🔥 Série en cours : **{stats['streak_value']} victoires consécutives !**")
        else:
            st.error(f"❄️ Série en cours : **{stats['streak_value']} défaites consécutives**")

    st.markdown("---")

    # ── Bilan général ────────────────────────────────────────────────────────
    st.markdown("### 🎯 Bilan général")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Victoires", stats["wins"])
    col2.metric("Défaites", stats["losses"])
    col3.metric("Matchs joués", stats["total"])
    col4.metric("Win rate", f"{stats['winrate']:.1f}%")

    col1, col2 = st.columns(2)
    col1.metric("Classement actuel", f"#{player.get('rank', '—')}")
    col2.metric("Meilleur classement", f"#{player.get('best_rank', '—')}")

    st.markdown("---")

    # ── Sets et points ───────────────────────────────────────────────────────
    st.markdown("### 🏓 Sets & Points")
    col1, col2, col3 = st.columns(3)
    col1.metric("Sets remportés", f"{stats['sets_won']} / {stats['sets_won'] + stats['sets_lost']}", f"{stats['sets_ratio']:.1f}%")
    col2.metric("Points remportés", f"{stats['pts_won']} / {stats['pts_won'] + stats['pts_lost']}", f"{stats['pts_ratio']:.1f}%")

    # Matchs en 5 sets
    if stats["total"] > 0:
        label_5sets = (
            f"{stats['five_set_wins']}V / {stats['five_set_losses']}D "
            f"({stats['five_set_ratio_of_all']:.0f}% des matchs)"
        )
        col3.metric("Matchs en 5 sets", label_5sets)

    st.markdown("---")

    # ── Performance selon le niveau de l'adversaire ──────────────────────────
    st.markdown("### 📈 Performance selon l'adversaire")
    col1, col2 = st.columns(2)

    total_vs_better = stats["wins_vs_better"] + stats["losses_vs_better"]
    total_vs_weaker = stats["wins_vs_weaker"] + stats["losses_vs_weaker"]
    wr_better = (stats["wins_vs_better"] / total_vs_better * 100) if total_vs_better > 0 else 0
    wr_weaker = (stats["wins_vs_weaker"] / total_vs_weaker * 100) if total_vs_weaker > 0 else 0

    with col1:
        st.markdown("**🔺 Contre mieux classés**")
        if total_vs_better > 0:
            st.write(f"{stats['wins_vs_better']}V / {stats['losses_vs_better']}D — win rate : **{wr_better:.1f}%**")
        else:
            st.caption("Aucun match contre un joueur mieux classé.")

    with col2:
        st.markdown("**🔻 Contre moins bien classés**")
        if total_vs_weaker > 0:
            st.write(f"{stats['wins_vs_weaker']}V / {stats['losses_vs_weaker']}D — win rate : **{wr_weaker:.1f}%**")
        else:
            st.caption("Aucun match contre un joueur moins bien classé.")

    st.markdown("---")

    # ── Rivaux ───────────────────────────────────────────────────────────────
    st.markdown("### ⚔️ Rivaux")

    def rival_detail(name):
        if not name:
            return "—"
        s = stats["opponent_stats"].get(name, {})
        w, l = s.get("wins", 0), s.get("losses", 0)
        return f"**{name}** — bilan {w}V / {l}D ({w+l} matchs)"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("😈 **Pire ennemi**")
        if stats["pire_ennemi"]:
            st.write(rival_detail(stats["pire_ennemi"]))
            s = stats["opponent_stats"].get(stats["pire_ennemi"], {})
            st.caption(f"{s.get('losses', 0)} défaite(s)")
        else:
            st.caption("Aucune défaite enregistrée")

    with col2:
        st.markdown("🎯 **Cible favorite**")
        if stats["cible_favorite"]:
            st.write(rival_detail(stats["cible_favorite"]))
            s = stats["opponent_stats"].get(stats["cible_favorite"], {})
            st.caption(f"{s.get('wins', 0)} victoire(s)")
        else:
            st.caption("Aucune victoire enregistrée")

    with col3:
        st.markdown("🤝 **Plus grand rival**")
        if stats["plus_grand_rival"]:
            st.write(rival_detail(stats["plus_grand_rival"]))
            s = stats["opponent_stats"].get(stats["plus_grand_rival"], {})
            st.caption(f"{s.get('wins',0)+s.get('losses',0)} matchs disputés ensemble")
        else:
            st.caption("Pas assez de matchs")

    st.markdown("---")

    # ── Graphique MMR ────────────────────────────────────────────────────────
    st.markdown("### 📉 Évolution du MMR")

    # Déterminer le n°1 et le joueur juste au-dessus
    rank1_name = active_players[0]["name"] if active_players else None
    current_rank = player.get("rank")
    rank1_plus1_name = None
    if current_rank and current_rank > 1:
        above = [p for p in active_players if p["rank"] == current_rank - 1]
        rank1_plus1_name = above[0]["name"] if above else None

    df = build_mmr_chart(
        player_name,
        stats["chart_players"],
        data,
        rank1_name,
        rank1_plus1_name,
    )

    if not df.empty:
        # Légende : renommer les colonnes avec des labels clairs
        rename_map = {}
        labels_used = set()
        for col in df.columns:
            label = col
            suffixes = []
            if col == player_name:
                suffixes.append("(vous)")
            if col == rank1_name and col != player_name:
                suffixes.append("n°1")
            if col == rank1_plus1_name and col != player_name:
                suffixes.append(f"#{current_rank - 1}")
            if col == stats["pire_ennemi"]:
                suffixes.append("pire ennemi")
            if col == stats["cible_favorite"]:
                suffixes.append("cible favorite")
            if col == stats["plus_grand_rival"] and col not in {stats["pire_ennemi"], stats["cible_favorite"]}:
                suffixes.append("rival")
            if suffixes:
                label = f"{col} ({', '.join(suffixes)})"
            rename_map[col] = label

        df_display = df.rename(columns=rename_map)
        st.line_chart(df_display, use_container_width=True)

        st.caption(
            "Courbes affichées : joueur sélectionné · n°1 actuel · "
            "joueur juste au-dessus · pire ennemi · cible favorite · plus grand rival "
            "(doublons automatiquement fusionnés)"
        )
    else:
        st.info("Pas d'historique MMR disponible.")

    st.markdown("---")

    # ── Historique des matchs ────────────────────────────────────────────────
    st.markdown("### 📋 Historique des matchs")

    if stats["match_history"]:
        df_hist = pd.DataFrame(stats["match_history"])
        st.dataframe(
            df_hist,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Résultat": st.column_config.TextColumn(width="medium"),
                "Date": st.column_config.TextColumn(width="small"),
                "Score": st.column_config.TextColumn(width="small"),
            }
        )
    else:
        st.info("Aucun match enregistré pour ce joueur.")
