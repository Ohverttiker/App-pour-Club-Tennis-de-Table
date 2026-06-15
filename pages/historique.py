import streamlit as st
from core.ranking import get_players, get_retired_players, get_matches, load_data

def show():
    st.markdown("## 📈 Historique & Évolution")

    with st.spinner("Chargement..."):
        data        = load_data()
        active      = get_players(data)
        retired     = get_retired_players(data)
        all_players = active + retired

    if not all_players:
        st.info("Aucun joueur enregistré.")
        return

    # ── Évolution MMR ─────────────────────────────────────────────────────────
    st.markdown("### 📊 Évolution du MMR")

    try:
        import pandas as pd
        import altair as alt

        active_names  = [p["name"] for p in active]
        retired_names = [p["name"] for p in retired]
        all_names     = active_names + retired_names

        

        # Labels avec mention (retraité) pour ne pas confondre
        label_map = {n: n for n in active_names}
        label_map.update({n: f"{n} (retraité)" for n in retired_names})

        selected_labels = st.multiselect(
            "Sélectionner les joueurs à afficher",
            options=[label_map[n] for n in all_names],
            default=[label_map[n] for n in all_names[:min(5, len(all_names))]]
        )

        # Inverser le label_map pour retrouver le vrai nom
        reverse_map = {v: k for k, v in label_map.items()}
        selected_names = [reverse_map[l] for l in selected_labels]

        if selected_names:
            rows = []
            for p in all_players:
                if p["name"] in selected_names:
                    label = label_map[p["name"]]
                    for entry in p.get("history", []):
                        rows.append({
                            "Joueur": label,
                            "Date":   entry["date"],
                            "MMR":    entry["mmr"]
                        })

            if rows:
                df = pd.DataFrame(rows)
                df["Date"] = pd.to_datetime(df["Date"])

                # MMR final pour chaque joueur
                final_mmr = {p["name"]: p["mmr"] for p in all_players}

                # Labels triés par MMR décroissant
                sorted_labels = sorted(
                    [label_map[n] for n in all_names],
                    key=lambda lbl: final_mmr[reverse_map[lbl]],
                    reverse=True
                )


                chart = alt.Chart(df).mark_line(point=True).encode(
                    x=alt.X("Date:T", title="Date"),
                    y=alt.Y("MMR:Q", title="MMR", scale=alt.Scale(zero=False)),
                    color=alt.Color("Joueur:N", sort=sorted_labels),
                    strokeDash=alt.condition(
                        alt.FieldOneOfPredicate(field="Joueur", oneOf=[label_map[n] for n in retired_names]),
                        alt.value([4, 4]),   # ligne pointillée pour les retraités
                        alt.value([0])
                    ),
                    tooltip=["Joueur", "Date", "MMR"]
                ).properties(height=350)

                st.altair_chart(chart, use_container_width=True)
                if retired_names:
                    st.caption("— — Ligne pointillée = joueur retraité")
            else:
                st.info("Pas encore assez d'historique.")
    except ImportError:
        st.warning("Installez pandas et altair : `pip install pandas altair`")

    st.markdown("---")

    # ── Historique des matchs ─────────────────────────────────────────────────
    st.markdown("### 📋 Historique des matchs")

    with st.spinner("Chargement des matchs..."):
        matches = get_matches(data)

    if not matches:
        st.info("Aucun match enregistré pour l'instant.")
    else:
        retired_set = {p["name"] for p in retired}
        for m in matches:
            col1, col2, col3 = st.columns([1.5, 3, 1])
            col1.caption(m["date"])

            winner_seed = m["rank_winner"]
            loser_seed = m["rank_loser"]

            winner_tag = " *(retraité)*" if m["winner"] in retired_set else ""
            loser_tag  = " *(retraité)*" if m["loser"]  in retired_set else ""
            col2.write(
                f"🟢 **[{winner_seed}] {m['winner']}**{winner_tag} bat "
                f"**[{loser_seed}] {m['loser']}**{loser_tag} ({m['score']})"
            )
            col3.write(f"+{m['sets_detail']}")

    st.markdown("---")

    # ── Stats globales ────────────────────────────────────────────────────────
    st.markdown("### 🏆 Stats globales")
    total_matches = len(get_matches(data))
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Joueurs actifs",   len(active))
    col2.metric("Joueurs retraités", len(retired))
    col3.metric("Matchs joués",     total_matches)

    if active:
        best = max(active, key=lambda p: p["wins"])
        col4.metric("Meilleur joueur", best["name"], f"{best['wins']} victoires")


show()