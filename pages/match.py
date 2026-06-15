import streamlit as st
from core.ranking import load_data, get_players, record_match, display_mmr
from datetime import *

data = load_data()

def show():
    st.markdown("## ⚔️ Saisir un résultat de match")

    use_custom_date = st.checkbox("Modifier la date et l'heure du match")

    if use_custom_date:
        col_date, col_time = st.columns(2)
        with col_date:
            match_date = st.date_input(
                "Date",
                value=datetime.now().date(),
                key="match_date"
            )
        with col_time:
            match_time = st.time_input(
                "Heure",
                value=datetime.now().time(),
                key="match_time"
            )

        match_datetime = f"{match_date} {match_time.strftime('%H:%M')}"
    else:
        match_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")

    players = get_players(data)
    if len(players) < 2:
        st.warning("Il faut au moins 2 joueurs pour enregistrer un match.")
        return

    names = [p["name"] for p in players]

    st.markdown("#### Sélectionner les joueurs")
    col1, col2 = st.columns(2)
    with col1:
        winner = st.selectbox("🏆 Vainqueur", names, key="winner")
    with col2:
        loser_options = [n for n in names if n != winner]
        loser = st.selectbox("😔 Perdant", loser_options, key="loser")

    st.markdown("#### Score du match")
    col3, col4 = st.columns(2)
    with col3:
        score_winner = st.number_input(f"Sets gagnés par {winner}", min_value=0, max_value=4, value=3)
    with col4:
        score_loser = st.number_input(f"Sets gagnés par {loser}", min_value=0, max_value=3, value=0)

    st.markdown("#### Détail des sets (optionnel)")
    sets_detail = st.text_input(
        "Exemple : 11-9 11-9 7-11 12-10",
        placeholder="Laisser vide si non renseigné"
    )

    # Aperçu MMR
    winner_data = next(p for p in players if p["name"] == winner)
    loser_data = next(p for p in players if p["name"] == loser)

    from core.ranking import calculate_elo_change
    change = calculate_elo_change(display_mmr(winner_data["mmr"]), display_mmr(loser_data["mmr"]),score_winner,score_loser)

    change_loser = score_winner-score_loser

    st.markdown("---")
    st.markdown("#### 📊 Aperçu des changements MMR")
    col5, col6 = st.columns(2)
    with col5:
        st.metric(
            label=f"🏆 {winner}",
            value=f"{display_mmr(winner_data['mmr']) + change} pts",
            delta=f"+{change} pts"
        )
    with col6:
        st.metric(
            label=f"😔 {loser}",
            value=f"{max(display_mmr(loser_data['mmr']) - change_loser, 100)} pts",
            delta=f"-{change_loser} pts"
        )

    st.markdown("")
    if st.button("✅ Valider le résultat", type="primary", use_container_width=True):
        if score_winner == score_loser:
            st.error("Le score ne peut pas être nul (égalité impossible en tennis de table).")
        else:
            ok, result = record_match(data, winner, loser, score_winner, score_loser, sets_detail, match_datetime)
            if ok:
                st.success(f"Match enregistré ! **{winner}** bat **{loser}** {score_winner}-{score_loser} (+{result} pts)")
                st.balloons()
            else:
                st.error(result)


show()