import streamlit as st
from core.ranking import load_data, get_players, get_retired_players, add_player, remove_player, retire_player, reactivate_player, display_mmr

data = load_data()
players = get_players(data)
start_mmr = int(players[-1]["mmr"])-4


def show():

    # ── Routing interne : page stats ─────────────────────────────────────────
    if st.session_state.get("selected_player"):
        from pages.stats_joueur import show as show_stats
        show_stats(st.session_state["selected_player"])
        return

    st.markdown("## 👥 Gestion des joueurs")

    # ── Ajouter ──────────────────────────────────────────────────────────────
    st.markdown("### ➕ Ajouter un joueur")
    with st.form("add_player_form"):
        col1, col2 = st.columns([2, 1])
        with col1:
            new_name = st.text_input("Nom du joueur")
        with col2:
            new_mmr = st.number_input("MMR de départ", min_value=100, max_value=3000, value=start_mmr, step=5)
        submitted = st.form_submit_button("Ajouter", type="primary", use_container_width=True)
        if submitted:
            if not new_name.strip():
                st.error("Le nom ne peut pas être vide.")
            else:
                try:
                    player = add_player(data, new_name.strip(), new_mmr)
                    st.success(f"Joueur ajouté : {player['name']} ({player['mmr']} MMR)")
                except ValueError as e:
                    st.error(str(e))

    st.markdown("---")

    # ── Joueurs actifs ────────────────────────────────────────────────────────
    st.markdown("### 🟢 Joueurs actifs")

    with st.spinner("Chargement..."):
        players = get_players(data)

    if not players:
        st.info("Aucun joueur actif pour l'instant.")
    else:
        st.caption("**Détails** affiche les stats · **Retirer** archive le joueur · **Supprimer** efface définitivement")
        for p in players:
            col1, col2, col3, col4, col5 = st.columns([0.5, 2.5, 1.0, 1.2, 1.2])
            col1.write(f"**#{p['rank']}**")
            col2.write(f"{p['name']} — {display_mmr(p['mmr'])} pts ({p['wins']}V / {p['losses']}D)")

            if col3.button("📊 Détails", key=f"stats_{p['name']}", use_container_width=True):
                st.session_state["selected_player"] = p["name"]
                st.rerun()

            if col4.button("🗄️ Retirer", key=f"retire_{p['name']}", use_container_width=True):
                with st.spinner("Mise à jour..."):
                    ok, msg = retire_player(p["name"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            if col5.button("🗑️ Supprimer", key=f"del_{p['name']}", use_container_width=True):
                with st.spinner("Suppression..."):
                    ok, msg = remove_player(data, p["name"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.markdown("---")

    # ── Joueurs retraités ─────────────────────────────────────────────────────
    st.markdown("### 🗄️ Joueurs retraités")

    with st.spinner("Chargement..."):
        retired = get_retired_players(data)

    if not retired:
        st.info("Aucun joueur retraité pour l'instant.")
        return

    for p in retired:
        retired_since = p.get("retired_date", "—")
        peak_mmr = max((e["mmr"] for e in p.get("history", [])), default=p["mmr"])

        with st.expander(f"**{p['name']}** — retraité le {retired_since} · pic classement : #{p["best_rank"]} · pic MMR : {display_mmr(peak_mmr)} pts"):
            st.write(f"Bilan avant retraite : **{p['wins']}V / {p['losses']}D**")

            col_stats, _ = st.columns([1, 2])
            with col_stats:
                if st.button("📊 Voir ses stats", key=f"stats_retired_{p['name']}", use_container_width=True):
                    st.session_state["selected_player"] = p["name"]
                    st.rerun()

            st.markdown("**Réactiver ce joueur**")

            col1, col2 = st.columns([1.5, 1])
            with col1:
                new_mmr = st.number_input(
                    "MMR de départ",
                    min_value=100, max_value=3000, value=start_mmr, step=5,
                    key=f"mmr_{p['name']}"
                )
            with col2:
                st.markdown("<div style='margin-top:1.9rem'>", unsafe_allow_html=True)
                if st.button("✅ Réactiver", key=f"reactivate_{p['name']}", use_container_width=True, type="primary"):
                    with st.spinner("Réactivation..."):
                        ok, msg = reactivate_player(p["name"], new_mmr)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                st.markdown("</div>", unsafe_allow_html=True)


show()
