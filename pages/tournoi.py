"""
Page Tournoi – Streamlit
"""

import streamlit as st
from core.ranking import load_data, get_players, record_match, get_everyone
from core.tournament_engine import (
    list_tournaments, load_tournament, save_tournament, delete_tournament,
    create_tournament, record_group_match, record_knockout_match,
    compute_group_standings, compute_global_chapeau_standings,
    get_group_completion, all_groups_complete,
    generate_knockout_from_groups, advance_knockout_round,
    compute_mmr_delta,
    add_custom_match, record_custom_match,
)
from datetime import datetime


# ─── Constantes UI ───────────────────────────────────────────────────────────

FORMAT_INFO = {
    "round_robin": {
        "label": "🔄 Round Robin",
        "desc": "Chaque joueur affronte tous les autres une fois. Simple et équitable.",
        "recommended": "4–10 joueurs",
    },
    "chapeau": {
        "label": "🎩 Format Chapeau",
        "desc": "3 niveaux, poules mixtes. Chaque joueur fait exactement 3 matchs. Classement global puis top N en phases finales.",
        "recommended": "9–24 joueurs",
    },
    "double_elim": {
        "label": "⚔️ Élimination Directe",
        "desc": "Arbre classique, Une défaite = Elimination",
        "recommended": "8–16 joueurs",
    },
    "custom": {
        "label": "🎲 Tournoi Personnalisé",
        "desc": "Ajoutez vos propres matchs librement, sans contrainte de structure.",
        "recommended": "Nombre libre",
    },
}

MMR_MODE_INFO = {
    "none": {
        "label": "🎭 Tournoi pour du beurre",
        "desc": "Aucun impact sur le classement MMR. Parfait pour s'entraîner.",
    },
    "sets_only": {
        "label": "📊 Différence de sets",
        "desc": "Seule la différence de sets impacte le classement (comme les matchs normaux).",
    },
    "sets_upset": {
        "label": "⚡ Sets + Bonus Upset",
        "desc": "Différence de sets + bonus si le moins bien classé gagne (environ rang_diff / 3 pts).",
    },
}

BO_OPTIONS = {3: "BO3 (max 3 sets)", 5: "BO5 (max 5 sets)", 7: "BO7 (max 7 sets)"}

STATUS_BADGE = {"in_progress": "🟡 En cours", "finished": "✅ Terminé"}


def _badge(status): return STATUS_BADGE.get(status, status)

def _needed(bo): return (bo // 2) + 1

def _score_valid(s1, s2, bo):
    n = _needed(bo)
    return (s1 == n or s2 == n) and s1 != s2

def _score_valid_custom(s1, s2, bo):
    n = _needed(bo)
    return (s1 >= n or s2 >= n) and s1 != s2


# ─── Entrée principale ───────────────────────────────────────────────────────

def show():
    st.markdown("## 🏆 Tournois")

    if "tournament_view" not in st.session_state:
        st.session_state.tournament_view = "list"
    if "active_tournament_id" not in st.session_state:
        st.session_state.active_tournament_id = None

    view = st.session_state.tournament_view

    if view == "list":
        _show_list()
    elif view == "create":
        _show_create()
    elif view == "play":
        tid = st.session_state.active_tournament_id
        t = load_tournament(tid)
        if t is None:
            st.error("Tournoi introuvable.")
            st.session_state.tournament_view = "list"
            st.rerun()
        else:
            _show_tournament(t)


# ─── Liste ───────────────────────────────────────────────────────────────────

def _show_list():
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.caption("Gérez vos tournois sauvegardés ou créez-en un nouveau.")
    with col_btn:
        if st.button("➕ Nouveau tournoi", type="primary", use_container_width=True):
            # Nettoyer les clés de création au cas où
            for k in ["create_format", "create_mmr_mode"]:
                st.session_state.pop(k, None)
            st.session_state.tournament_view = "create"
            st.rerun()

    tournaments = list_tournaments()
    if not tournaments:
        st.info("Aucun tournoi enregistré. Créez-en un !")
        return

    in_progress = [t for t in tournaments if t["status"] == "in_progress"]
    finished    = [t for t in tournaments if t["status"] == "finished"]

    if in_progress:
        st.markdown("### 🟡 Tournois en cours")
        for t in in_progress:
            _tournament_card(t)
    if finished:
        st.markdown("### ✅ Tournois terminés")
        for t in finished:
            _tournament_card(t)


def _tournament_card(t: dict):
    with st.container(border=True):
        col1, col2, col3 = st.columns([4, 2, 2])
        with col1:
            fmt_label = FORMAT_INFO.get(t["format"], {}).get("label", t["format"])
            mmr_label = MMR_MODE_INFO.get(t.get("mmr_mode", "none"), {}).get("label", "")
            st.markdown(
                f"**{t['name']}**  \n"
                f"{fmt_label} · {t['players_count']} joueurs · {t['created_at']}  \n"
                f"<small>{mmr_label}</small>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            label = "▶️ Reprendre" if t["status"] == "in_progress" else "🔍 Consulter"
            if st.button(label, key=f"open_{t['id']}", use_container_width=True):
                st.session_state.active_tournament_id = t["id"]
                st.session_state.tournament_view = "play"
                st.rerun()
        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Supprimer", key=f"del_{t['id']}", use_container_width=True):
                delete_tournament(t["id"])
                st.rerun()


# ─── Création ────────────────────────────────────────────────────────────────

def _show_create():
    if st.button("← Retour à la liste"):
        st.session_state.tournament_view = "list"
        st.rerun()

    st.markdown("### ➕ Créer un nouveau tournoi")

    data = load_data()
    all_players = get_everyone(data)
    if len(all_players) < 2:
        st.warning("Il faut au moins 2 joueurs actifs dans l'application.")
        return

    # ── 1. Nom ────────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 1️⃣ Nom du tournoi")
        name = st.text_input("Nom", placeholder="Tournoi juin 2026",
                             label_visibility="collapsed")

    # ── 2. Format ─────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 2️⃣ Format")
        selected_format = st.session_state.get("create_format", "chapeau")
        fmt_cols = st.columns(4)
        for i, (fkey, finfo) in enumerate(FORMAT_INFO.items()):
            with fmt_cols[i]:
                is_sel = selected_format == fkey
                border = "2px solid #4CAF50" if is_sel else "1px solid #555"
                st.markdown(
                    f'<div style="border:{border};border-radius:8px;padding:12px;min-height:140px">'
                    f'<b>{finfo["label"]}</b><br>'
                    f'<small style="color:#aaa">{finfo["desc"]}</small><br><br>'
                    f'<small>👥 {finfo["recommended"]}</small></div>',
                    unsafe_allow_html=True,
                )
                btn_label = "✅ Sélectionné" if is_sel else "Choisir"
                if st.button(btn_label, key=f"fmt_{fkey}", use_container_width=True):
                    st.session_state.create_format = fkey
                    st.rerun()

    selected_format = st.session_state.get("create_format", "chapeau")

    # ── 3. Format des matchs ──────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 3️⃣ Format des matchs")
        bo = st.radio(
            "Best-of", options=list(BO_OPTIONS.keys()),
            format_func=lambda x: BO_OPTIONS[x],
            horizontal=True, index=0, label_visibility="collapsed",
        )

    # ── 4. Impact MMR ─────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 4️⃣ Impact sur le classement MMR")
        selected_mmr = st.session_state.get("create_mmr_mode", "none")
        mmr_cols = st.columns(3)
        for i, (mkey, minfo) in enumerate(MMR_MODE_INFO.items()):
            with mmr_cols[i]:
                is_sel = selected_mmr == mkey
                border = "2px solid #4CAF50" if is_sel else "1px solid #555"
                st.markdown(
                    f'<div style="border:{border};border-radius:8px;padding:12px;min-height:110px">'
                    f'<b>{minfo["label"]}</b><br>'
                    f'<small style="color:#aaa">{minfo["desc"]}</small></div>',
                    unsafe_allow_html=True,
                )
                btn_label = "✅ Sélectionné" if is_sel else "Choisir"
                if st.button(btn_label, key=f"mmr_{mkey}", use_container_width=True):
                    st.session_state.create_mmr_mode = mkey
                    st.rerun()

    selected_mmr = st.session_state.get("create_mmr_mode", "none")

    # ── 5. Participants ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 5️⃣ Participants")
        player_names = [p["name"] for p in all_players]
        col_sel, col_info = st.columns([3, 1])
        with col_sel:
            selected_names = st.multiselect(
                "Joueurs", options=player_names, default=player_names,
                label_visibility="collapsed",
            )
        with col_info:
            st.metric("Sélectionnés", len(selected_names))

        if selected_names and selected_format == "chapeau" and len(selected_names) >= 3:
            sel_players = sorted(
                [p for p in all_players if p["name"] in selected_names],
                key=lambda p: p["mmr"], reverse=True,
            )
            n = len(sel_players)
            third = n // 3
            hats = [sel_players[:third], sel_players[third:2*third], sel_players[2*third:]]
            hat_labels = ["🥇 Chapeau 1 (Meilleurs)", "🥈 Chapeau 2", "🥉 Chapeau 3 (Débutants)"]
            st.markdown("**Aperçu des chapeaux :**")
            hat_cols = st.columns(3)
            for j, (hat, lbl) in enumerate(zip(hats, hat_labels)):
                with hat_cols[j]:
                    st.markdown(f"**{lbl}**")
                    for p in hat:
                        st.caption(f"• {p['name']} ({int(p['mmr'])} pts)")

    # ── Validation ────────────────────────────────────────────────────────────
    st.markdown("")
    can_create = (
        name.strip()
        and len(selected_names) >= 2
        and (selected_format != "chapeau" or len(selected_names) >= 3)
    )
    if not name.strip():
        st.warning("Renseignez un nom pour le tournoi.")
    elif len(selected_names) < 2:
        st.warning("Sélectionnez au moins 2 joueurs.")
    elif selected_format == "chapeau" and len(selected_names) < 3:
        st.warning("Le format Chapeau nécessite au moins 3 joueurs.")

    if st.button("🚀 Lancer le tournoi", type="primary",
                 use_container_width=True, disabled=not can_create):
        sel_players = [p for p in all_players if p["name"] in selected_names]
        t = create_tournament(
            name=name.strip(), fmt=selected_format,
            players=sel_players, bo=bo, mmr_mode=selected_mmr,
        )
        for k in ["create_format", "create_mmr_mode"]:
            st.session_state.pop(k, None)
        st.session_state.active_tournament_id = t["id"]
        st.session_state.tournament_view = "play"
        st.rerun()


# ─── Affichage d'un tournoi ───────────────────────────────────────────────────

def _show_tournament(t: dict):
    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("← Retour"):
            st.session_state.tournament_view = "list"
            st.session_state.active_tournament_id = None
            st.rerun()
    with col_title:
        fmt_label = FORMAT_INFO.get(t["format"], {}).get("label", t["format"])
        mmr_label = MMR_MODE_INFO.get(t.get("mmr_mode", "none"), {}).get("label", "")
        st.markdown(f"### {t['name']}")
        st.caption(f"{fmt_label} · BO{t['bo']} · {mmr_label} · {_badge(t['status'])} · {t['created_at']}")

    st.markdown("---")

    phase = t.get("phase", "group")

    if phase == "custom":
        _show_custom_phase(t)
    elif phase == "group" and t.get("groups"):
        _show_group_phase(t)
    elif phase == "knockout" and t.get("knockout"):
        _show_knockout_phase(t)
    elif phase == "done":
        _show_results(t)


# ─── Phase de poules ─────────────────────────────────────────────────────────

def _show_group_phase(t: dict):
    groups = t["groups"]
    bo = t["bo"]
    needed = _needed(bo)
    is_chapeau = t["format"] == "chapeau"

    # Progression globale
    total_played = sum(get_group_completion(g)[0] for g in groups)
    total_all    = sum(get_group_completion(g)[1] for g in groups)
    pct = total_played / total_all if total_all else 0
    st.progress(pct, text=f"Progression : {total_played}/{total_all} matchs joués")

    # ── Onglets poules + classement global (chapeau) ──────────────────────────
    tab_names = [f"{g['name']} ({get_group_completion(g)[0]}/{get_group_completion(g)[1]})"
                 for g in groups]
    if is_chapeau:
        tab_names.append("🌍 Classement général")

    tabs = st.tabs(tab_names)

    for tab, group in zip(tabs[:len(groups)], groups):
        with tab:
            _render_group(t, group, bo, needed)

    # Onglet classement global chapeau
    if is_chapeau:
        with tabs[-1]:
            _render_global_standings(t)

    # ── Passage en phases finales ─────────────────────────────────────────────
    st.markdown("---")
    done = all_groups_complete(t)

    if done:
        st.success("✅ Toutes les poules sont terminées ! Génération des phases finales possible.")
        max_qualifiable = len(t["players"])
        top_n_opts = [n for n in [4, 8, 16] if n <= max_qualifiable]
        if not top_n_opts:
            top_n_opts = [max_qualifiable]

        col_n, col_go = st.columns([2, 2])
        with col_n:
            top_n = st.selectbox(
                "Qualifiés pour les phases finales",
                options=top_n_opts,
                format_func=lambda x: f"Top {x}",
                key="top_n_select",
            )
        with col_go:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🏆 Générer les phases finales", type="primary",
                         use_container_width=True):
                generate_knockout_from_groups(t, top_n=top_n)
                st.rerun()
    else:
        remaining = total_all - total_played
        st.info(f"⏳ {remaining} match(s) restant(s) avant de pouvoir générer les phases finales.")


def _render_group(t: dict, group: dict, bo: int, needed: int):
    col_matches, col_standing = st.columns([3, 2])

    with col_matches:
        st.markdown("#### Matchs")

        # Afficher la composition des chapeaux si format chapeau
        if t["format"] == "chapeau" and group.get("hat_info"):
            hats_text = " · ".join(
                f"Chapeau {h['hat']}: **{h['player']}**"
                for h in group["hat_info"]
            )
            st.caption(hats_text)

        for m in group["matches"]:
            if m["played"]:
                _display_played_match(m)
            else:
                _display_match_form(t, group["id"], m, bo, needed)

    with col_standing:
        st.markdown("#### Classement poule")
        standings = compute_group_standings(group)
        _render_standings_table(standings)


def _render_global_standings(t: dict):
    st.markdown("#### 🌍 Classement général")
    st.caption("Agrégé sur toutes les poules. Sert de base pour la qualification en phases finales.")
    standings = compute_global_chapeau_standings(t)
    _render_standings_table(standings, show_group_rank=False)


def _render_standings_table(standings: list, show_group_rank: bool = True):
    medals = ["🥇", "🥈", "🥉"]
    for s in standings:
        diff = s["sets_won"] - s["sets_lost"]
        diff_str = f"+{diff}" if diff >= 0 else str(diff)
        medal = medals[s["rank"] - 1] if s["rank"] <= 3 else f"**{s['rank']}.**"
        st.markdown(
            f"{medal} **{s['player']}** — "
            f"{s['wins']}V {s['losses']}D — "
            f"sets {diff_str} ({s['sets_won']}/{s['sets_lost']})"
        )


def _display_played_match(m: dict):
    p1_icon = "🏆 " if m["winner"] == m["p1"] else ""
    p2_icon = " 🏆" if m["winner"] == m["p2"] else ""
    st.success(
        f"{p1_icon}**{m['p1']}** {m['score_p1']}-{m['score_p2']} **{m['p2']}**{p2_icon} : {m["sets_detail"]}",
        icon="✅",
    )


def _display_match_form(t: dict, group_id: str, m: dict, bo: int, needed: int):
    with st.expander(f"⚔️ {m['p1']} vs {m['p2']}", expanded=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            winner_sel = st.selectbox("Vainqueur", [m["p1"], m["p2"]], key=f"w_{m['id']}")
        with c2:
            sc_w = st.number_input("Sets gagnant", min_value=0, max_value=bo,
                                   value=needed, key=f"sw_{m['id']}")
        with c3:
            sc_l = st.number_input("Sets perdant", min_value=0, max_value=bo - 1,
                                   value=0, key=f"sl_{m['id']}")

        score_p1 = sc_w if winner_sel == m["p1"] else sc_l
        score_p2 = sc_l if winner_sel == m["p1"] else sc_w

        st.markdown("#### Détail des sets (optionnel)")
        sets_detail = st.text_input(
            "Exemple : 11-9 11-9 7-11 12-10",
            placeholder="Laisser vide si non renseigné",
            key=f"sets_detail_{m["id"]}"
        )

        if not _score_valid(score_p1, score_p2, bo):
            st.warning(f"Score invalide : le vainqueur doit avoir {needed} sets.")

        if st.button("✅ Valider", key=f"val_{m['id']}", use_container_width=True):
            if _score_valid(score_p1, score_p2, bo):
                record_group_match(t, group_id, m["id"], winner_sel, score_p1, score_p2, sets_detail)
                st.rerun()
            else:
                st.error("Score invalide.")


# ─── Phase finale ─────────────────────────────────────────────────────────────

def _show_knockout_phase(t: dict):
    ko = t["knockout"]
    bo = t["bo"]
    needed = _needed(bo)

    if t.get("phase") == "done" or ko.get("champion"):
        _show_results(t)
        return

    # Joueurs qualifiés (tête de série)
    if ko.get("qualified"):
        with st.expander("👥 Têtes de série", expanded=False):
            cols = st.columns(4)
            for i, p in enumerate(ko["qualified"]):
                with cols[i % 4]:
                    st.markdown(f"**#{i + 1}** {p}")

    st.markdown("### Phases finales")

    rounds = ko.get("rounds", [])
    for round_idx, round_matches in enumerate(rounds):
        if not round_matches:
            continue
        round_name = round_matches[0].get("round_name", f"Tour {round_idx + 1}")
        st.markdown(f"#### {round_name}")

        is_current = round_idx == len(rounds) - 1

        for m in round_matches:
            if m["played"]:
                _display_played_match(m)
            elif is_current:
                _display_ko_match_form(t, m, bo, needed)
            else:
                st.info(f"⏳ {m['p1']} vs {m['p2']} — en attente")

        st.markdown("")


def _display_ko_match_form(t: dict, m: dict, bo: int, needed: int):
    with st.expander(f"⚔️ {m['p1']} vs {m['p2']}", expanded=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            winner_sel = st.selectbox("Vainqueur", [m["p1"], m["p2"]], key=f"kow_{m['id']}")
        with c2:
            sc_w = st.number_input("Sets gagnant", min_value=0, max_value=bo,
                                   value=needed, key=f"kosw_{m['id']}")
        with c3:
            sc_l = st.number_input("Sets perdant", min_value=0, max_value=bo - 1,
                                   value=0, key=f"kosl_{m['id']}")

        score_p1 = sc_w if winner_sel == m["p1"] else sc_l
        score_p2 = sc_l if winner_sel == m["p1"] else sc_w
        
        st.markdown("#### Détail des sets (optionnel)")
        sets_detail = st.text_input(
            "Exemple : 11-9 11-9 7-11 12-10",
            placeholder="Laisser vide si non renseigné",
            key=f"sets_detail_{m["id"]}"
        )

        if not _score_valid(score_p1, score_p2, bo):
            st.warning(f"Score invalide : le vainqueur doit avoir {needed} sets.")

        if st.button("✅ Valider", key=f"koval_{m['id']}", use_container_width=True):
            if _score_valid(score_p1, score_p2, bo):
                record_knockout_match(t, m["id"], winner_sel, score_p1, score_p2, sets_detail)
                st.rerun()
            else:
                st.error("Score invalide.")

def _show_custom_phase(t:dict):
    matches = t.get("custom_matches",[])
    bo = t["bo"]
    needed = _needed(bo)

    played = sum(1 for m in matches if m["played"])
    st.caption(f"{len(matches)} matchs créés · {played} joués")
    
    # ── Matchs existants ──────────────────────────────────────────────────
    if matches:
        st.markdown("### 📋 Matchs")
        for m in matches:
            if m["played"]:
                _display_played_match(m)
            else:
                _display_custom_match_form(t, m)
    else:
        st.info("Aucun match pour l'instant. Ajoutez-en un ci-dessous !")
    
    # ── Ajout d'un nouveau match ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ➕ Ajouter un match")

    
    names = [p["name"] for p in t["players"]]

    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            p1 = st.selectbox("🔵 Joueur 1", names, key="p1")
        with col2:
            p2_options = [n for n in names if n != p1]
            p2 = st.selectbox("🔴 Joueur 2", p2_options, key="p2")
        with col3:
            bo_match = st.selectbox(
                "Format", options=list(BO_OPTIONS.keys()),
                format_func=lambda x: BO_OPTIONS[x], key="custom_bo"
            )

        if st.button("➕ Créer le match", type="primary",
                     use_container_width=True):
            add_custom_match(t, p1.strip(), p2.strip(), bo_match)
            st.rerun()

    # ── Terminer le tournoi ───────────────────────────────────────────────
    st.markdown("---")
    if matches and all(m["played"] for m in matches):
        if st.button("🏁 Terminer le tournoi", type="primary",
                     use_container_width=True):
            t["status"] = "finished"
            t["phase"] = "done"
            save_tournament(t)
            st.rerun()

def _display_custom_match_form(t: dict, m: dict):
    bo = m.get("bo", t["bo"])
    needed = _needed(bo)
    
    sc_s4j1 = 0
    sc_s4j2 = 0
    sc_s5j1 = 0
    sc_s5j2 = 0
    sc_s6j1 = 0
    sc_s6j2 = 0
    sc_s7j1 = 0
    sc_s7j2 = 0
    with st.expander(f"⚔️ {m['p1']} vs {m['p2']}", expanded=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            winner_sel = st.selectbox("Vainqueur", [m["p1"], m["p2"]], key=f"cw_{m['id']}")
        with c2:
            sc_s1j1 = st.number_input("Score J1 Set 1", min_value=0, max_value = 1000,
                                   value=11, key=f"css1j1_{m['id']}")
        with c3:
            sc_s1j2 = st.number_input("Score J2 Set 1", min_value=0, max_value = 1000,
                                   value=7, key=f"css1j2_{m['id']}")
            
        c1, c2, c3 = st.columns([2, 1, 1])
        with c2:
            sc_s2j1 = st.number_input("Score J1 Set 2", min_value=0, max_value = 1000,
                                   value=11, key=f"css2j1_{m['id']}")
        with c3:
            sc_s2j2 = st.number_input("Score J2 Set 2", min_value=0, max_value = 1000,
                                   value=7, key=f"css2j2_{m['id']}")
            
        c1, c2, c3 = st.columns([2, 1, 1])
        with c2:
            sc_s3j1 = st.number_input("Score J1 Set 3", min_value=0, max_value = 1000,
                                   value=0, key=f"css3j1_{m['id']}")
        with c3:
            sc_s3j2 = st.number_input("Score J2 Set 3", min_value=0, max_value = 1000,
                                   value=0, key=f"css3j2_{m['id']}")
            
        if(bo>3):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c2:
                sc_s4j1 = st.number_input("Score J1 Set 4", min_value=0, max_value = 1000,
                                    value=0, key=f"css4j1_{m['id']}")
            with c3:
                sc_s4j2 = st.number_input("Score J2 Set 4", min_value=0, max_value = 1000,
                                    value=0, key=f"css4j2_{m['id']}")
                
            c1, c2, c3 = st.columns([2, 1, 1])
            with c2:
                sc_s5j1 = st.number_input("Score J1 Set 5", min_value=0, max_value = 1000,
                                    value=0, key=f"css5j1_{m['id']}")
            with c3:
                sc_s5j2 = st.number_input("Score J2 Set 5", min_value=0, max_value = 1000,
                                    value=0, key=f"css5j2_{m['id']}")
                
        if(bo>5):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c2:
                sc_s6j1 = st.number_input("Score J1 Set 6", min_value=0, max_value = 1000,
                                    value=0, key=f"css6j1_{m['id']}")
            with c3:
                sc_s6j2 = st.number_input("Score J2 Set 6", min_value=0, max_value = 1000,
                                    value=0, key=f"css6j2_{m['id']}")
                
            c1, c2, c3 = st.columns([2, 1, 1])
            with c2:
                sc_s7j1 = st.number_input("Score J1 Set 7", min_value=0, max_value = 1000,
                                    value=0, key=f"css7j1_{m['id']}")
            with c3:
                sc_s7j2 = st.number_input("Score J2 Set 7", min_value=0, max_value = 1000,
                                    value=0, key=f"css7j2_{m['id']}")

        setsJ1 = 0
        setsJ2 = 0
        if(sc_s1j1>sc_s1j2):
            setsJ1+=1
        else:
            setsJ2+=1
        if(sc_s2j1>sc_s2j2):
            setsJ1+=1
        else:
            setsJ2+=1
        #Set 3
        if(sc_s3j1>sc_s3j2):
            setsJ1+=1
        elif(sc_s3j2>sc_s3j1):
            setsJ2+=1

        #Set 4
        if(sc_s4j1>sc_s4j2):
            setsJ1+=1
        elif(sc_s4j2>sc_s4j1):
            setsJ2+=1

        #Set 5
        if(sc_s5j1>sc_s5j2):
            setsJ1+=1
        elif(sc_s5j2>sc_s5j1):
            setsJ2+=1

        #Set 6
        if(sc_s6j1>sc_s6j2):
            setsJ1+=1
        elif(sc_s6j2>sc_s6j1):
            setsJ2+=1
        #Set 7
        if(sc_s7j1>sc_s7j2):
            setsJ1+=1
        elif(sc_s7j2>sc_s7j1):
            setsJ2+=1

        if not _score_valid_custom(setsJ1, setsJ2, bo):
            st.warning(f"Score invalide : le vainqueur doit avoir {needed} sets ou plus.")

        if st.button("✅ Valider", key=f"cval_{m['id']}", use_container_width=True):
            if _score_valid_custom(setsJ1, setsJ2, bo):
                if(winner_sel == m['p2']):
                    sets_details = f"{sc_s1j2}-{sc_s1j1} {sc_s2j2}-{sc_s2j1}"
                    if(sc_s3j2>=11 or sc_s3j1 >= 11):
                        sets_details = f"{sc_s1j2}-{sc_s1j1} {sc_s2j2}-{sc_s2j1} {sc_s3j2}-{sc_s3j1}"
                    if(sc_s4j2>=11 or sc_s4j1 >= 11):
                        sets_details = f"{sc_s1j2}-{sc_s1j1} {sc_s2j2}-{sc_s2j1} {sc_s3j2}-{sc_s3j1} {sc_s4j2}-{sc_s4j1}"
                    if(sc_s5j2>=11 or sc_s5j1 >= 11):
                        sets_details = f"{sc_s1j2}-{sc_s1j1} {sc_s2j2}-{sc_s2j1} {sc_s3j2}-{sc_s3j1} {sc_s4j2}-{sc_s4j1} {sc_s5j2}-{sc_s5j1}"
                    if(sc_s6j2>=11 or sc_s6j1 >= 11):
                        sets_details = f"{sc_s1j2}-{sc_s1j1} {sc_s2j2}-{sc_s2j1} {sc_s3j2}-{sc_s3j1} {sc_s4j2}-{sc_s4j1} {sc_s5j2}-{sc_s5j1} {sc_s6j2}-{sc_s6j1}"
                    if(sc_s7j2>=11 or sc_s7j1 >= 11):
                        sets_details = f"{sc_s1j2}-{sc_s1j1} {sc_s2j2}-{sc_s2j1} {sc_s3j2}-{sc_s3j1} {sc_s4j2}-{sc_s4j1} {sc_s5j2}-{sc_s5j1} {sc_s6j2}-{sc_s6j1} {sc_s7j2}-{sc_s7j1}"
                    record_custom_match(t, m["id"], winner_sel, setsJ2, setsJ1, sets_details)
                else :
                    sets_details = f"{sc_s1j1}-{sc_s1j2} {sc_s2j1}-{sc_s2j2}"
                    if(sc_s3j2>=11 or sc_s3j1 >= 11):
                        sets_details = f"{sc_s1j1}-{sc_s1j2} {sc_s2j1}-{sc_s2j2} {sc_s3j1}-{sc_s3j2}"
                    if(sc_s4j2>=11 or sc_s4j1 >= 11):
                        sets_details = f"{sc_s1j1}-{sc_s1j2} {sc_s2j1}-{sc_s2j2} {sc_s3j1}-{sc_s3j2} {sc_s4j1}-{sc_s4j2}"
                    if(sc_s5j2>=11 or sc_s5j1 >= 11):
                        sets_details = f"{sc_s1j1}-{sc_s1j2} {sc_s2j1}-{sc_s2j2} {sc_s3j1}-{sc_s3j2} {sc_s4j1}-{sc_s4j2} {sc_s5j1}-{sc_s5j2}"
                    if(sc_s6j2>=11 or sc_s6j1 >= 11):
                        sets_details = f"{sc_s1j1}-{sc_s1j2} {sc_s2j1}-{sc_s2j2} {sc_s3j1}-{sc_s3j2} {sc_s4j1}-{sc_s4j2} {sc_s5j1}-{sc_s5j2} {sc_s6j1}-{sc_s6j2}"
                    if(sc_s7j2>=11 or sc_s7j1 >= 11):
                        sets_details = f"{sc_s1j1}-{sc_s1j2} {sc_s2j1}-{sc_s2j2} {sc_s3j1}-{sc_s3j2} {sc_s4j1}-{sc_s4j2} {sc_s5j1}-{sc_s5j2} {sc_s6j1}-{sc_s6j2} {sc_s7j1}-{sc_s7j2}"
                    record_custom_match(t, m["id"], winner_sel, setsJ1, setsJ2, sets_details)


                st.rerun()
            else:
                st.error("Score invalide.")


# ─── Résultats finaux ─────────────────────────────────────────────────────────

def _show_results(t: dict):
    ko = t.get("knockout") or {}
    champion = ko.get("champion")

    matches = t.get("custom_matches",[])

    if champion:
        st.balloons()
        st.markdown(
            f'<div style="text-align:center;padding:30px;'
            f'background:linear-gradient(135deg,#1a1a2e,#16213e);'
            f'border-radius:16px;border:2px solid gold">'
            f'<h1>🏆</h1><h2 style="color:gold">{champion}</h2>'
            f'<p style="color:#ccc">Champion du tournoi <b>{t["name"]}</b></p></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")

    # Résumé des phases finales
    if ko.get("rounds"):
        st.markdown("### 📋 Résumé des phases finales")
        for round_matches in ko["rounds"]:
            if round_matches:
                rname = round_matches[0].get("round_name", "Tour")
                st.markdown(f"**{rname}**")
                for m in round_matches:
                    if m["played"] and m["winner"]:
                        loser = m["p2"] if m["winner"] == m["p1"] else m["p1"]
                        st.markdown(f"- 🏆 **{m['winner']}** bat {loser} {m['score_p1']}–{m['score_p2']}")

    # Résumé des poules (chapeau)
    if t["format"] == "chapeau" and t.get("groups"):
        with st.expander("📊 Classement final des poules", expanded=False):
            _render_global_standings(t)

    # ── Enregistrement MMR ─────────────────────────────────────────────────────
    mmr_mode = t.get("mmr_mode", "none")
    st.markdown("---")

    if mmr_mode == "none":
        st.info("🎭 Ce tournoi était pour du beurre — aucun impact sur le classement MMR.")
    else:
        mode_label = MMR_MODE_INFO.get(mmr_mode, {}).get("label", mmr_mode)
        with st.expander(f"📊 Enregistrer les résultats dans le classement MMR ({mode_label})", expanded=False):
            st.warning(
                "Cette action va enregistrer tous les matchs du tournoi dans le classement "
                "général et mettre à jour les MMR de façon permanente."
            )

            if st.button("⚠️ Confirmer l'enregistrement MMR", type="secondary",
                         use_container_width=True, key="confirm_mmr"):
                _do_record_mmr(t)

    if st.button("← Retour à la liste des tournois", use_container_width=True):
        st.session_state.tournament_view = "list"
        st.session_state.active_tournament_id = None
        st.rerun()

    if matches:
        st.markdown("### 📋 Matchs")
        for m in matches:
            if m["played"]:
                _display_played_match(m)


def _do_record_mmr(t: dict):
    """Enregistre tous les matchs du tournoi dans players.json."""
    data = load_data()
    mmr_mode = t.get("mmr_mode", "none")
    count = 0
    errors = []

    # Récupérer le MMR actuel des joueurs pour le calcul upset
    player_mmr = {p["name"]: p["mmr"] for p in data.get("players", [])}

    def _record(winner, loser, sp1, sp2):
        nonlocal count
        w_mmr = player_mmr.get(winner, 1200)
        l_mmr = player_mmr.get(loser, 1200)
        dw, dl = compute_mmr_delta(w_mmr, l_mmr, sp1, sp2, mmr_mode)

        if mmr_mode == "none":
            return  # ne devrait pas arriver ici

        # On utilise record_match avec les bons sets pour sets_only
        # Pour sets_upset on passe par un score fictif équivalent au delta calculé
        ok, msg = record_match(
            data, winner, loser, sp1, sp2, "", t["created_at"]
        )
        if ok:
            count += 1
            # Mettre à jour le MMR local pour les calculs suivants
            player_mmr[winner] = player_mmr.get(winner, 1200) + dw
            player_mmr[loser]  = player_mmr.get(loser, 1200) + dl
        else:
            errors.append(str(msg))

    # Matchs de poule
    for group in (t.get("groups") or []):
        for m in group["matches"]:
            if m["played"] and m["winner"]:
                loser = m["p2"] if m["winner"] == m["p1"] else m["p1"]
                _record(m["winner"], loser, m["score_p1"], m["score_p2"])

    # Matchs KO
    ko = t.get("knockout") or {}
    for round_matches in (ko.get("rounds") or []):
        for m in round_matches:
            if m["played"] and m["winner"]:
                loser = m["p2"] if m["winner"] == m["p1"] else m["p1"]
                _record(m["winner"], loser, m["score_p1"], m["score_p2"])

    if count:
        st.success(f"✅ {count} matchs enregistrés dans le classement !")
    for e in errors:
        st.error(e)

show()