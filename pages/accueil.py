import streamlit as st
from core.ranking import load_data, get_players, get_matches, display_mmr, get_rank_evolution

data = load_data()
players = get_players(data)
matches = get_matches(data)

def _evo_badge(delta: int) -> str:
    if delta > 0:
        return f"<span style='color:#2ecc71; font-weight:bold;'>▲ {delta}</span>"
    elif delta < 0:
        return f"<span style='color:#e74c3c; font-weight:bold;'>▼ {abs(delta)}</span>"
    return "<span style='color:#888;'>—</span>"

def show():
    st.markdown("""
    <div style='text-align:center; padding: 1rem 0 0.5rem 0;'>
        <span style='font-size:2.8rem;'>🏓</span>
        <h1 style='margin:0; font-size:2rem;'>Classement du Club</h1>
    </div>
    """, unsafe_allow_html=True)

    if not players:
        st.info("Aucun joueur pour l'instant. Ajoutez des joueurs dans la section **Gestion des joueurs**.")
        return

    # Podium top 3
    if len(players) >= 3:
        st.markdown("### 🥇 Podium")
        col2, col1, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div style='text-align:center; background:#FFD700; padding:1rem; border-radius:12px;'>
                <div style='font-size:2rem;'>🥇</div>
                <div style='font-weight:bold; font-size:1.1rem;'>{players[0]['name']}</div>
                <div style='font-size:1.3rem; font-weight:bold;'>{display_mmr(players[0]['mmr'])} pts</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div style='text-align:center; background:#C0C0C0; padding:1rem; border-radius:12px; margin-top:1.5rem;'>
                <div style='font-size:1.8rem;'>🥈</div>
                <div style='font-weight:bold;'>{players[1]['name']}</div>
                <div style='font-size:1.2rem; font-weight:bold;'>{display_mmr(players[1]['mmr'])} pts</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div style='text-align:center; background:#CD7F32; padding:1rem; border-radius:12px; margin-top:2.5rem;'>
                <div style='font-size:1.6rem;'>🥉</div>
                <div style='font-weight:bold;'>{players[2]['name']}</div>
                <div style='font-size:1.1rem; font-weight:bold;'>{display_mmr(players[2]['mmr'])} pts</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # Tableau complet
    st.markdown("### 📋 Classement complet")
    evolution = get_rank_evolution(data)

    header = st.columns([0.5, 2.5, 1.5, 1, 1, 1.5, 1])
    header[0].markdown("**#**")
    header[1].markdown("**Joueur**")
    header[2].markdown("**MMR**")
    header[3].markdown("**✅ V**")
    header[4].markdown("**❌ D**")
    header[5].markdown("**% Victoires**")
    header[6].markdown("**Évol.**")

    st.markdown("<hr style='margin:0.3rem 0;'>", unsafe_allow_html=True)

    for p in players:
        total = p["wins"] + p["losses"]
        winrate = f"{round(p['wins'] / total * 100)}%" if total > 0 else "—"
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(p["rank"], "")
        delta = evolution.get(p["name"])

        row = st.columns([0.5, 2.5, 1.5, 1, 1, 1.5, 1])
        row[0].write(f"{p['rank']}")
        row[1].write(f"{medal} {p['name']}")
        row[2].write(f"**{display_mmr(p['mmr'])}**")
        row[3].write(str(p["wins"]))
        row[4].write(str(p["losses"]))
        row[5].write(winrate)
        if delta is not None:
            row[6].markdown(_evo_badge(delta), unsafe_allow_html=True)
        else:
            row[6].write("🆕")  # joueur absent du backup = nouveau

    # Derniers matchs
    if matches:
        st.markdown("---")
        st.markdown("### 📅 Meilleurs Matchs")
        for m in matches:
            if m["delta"]==1:
                st.markdown(
                    f"{m['date']} - "
                    f"**[{m["rank_winner"]}] {m['winner']}** bat **[{m["rank_loser"]}] {m['loser']}** -  ({m['score']} : {m["sets_detail"]})"
                )

show()