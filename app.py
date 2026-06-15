import streamlit as st
from core.ranking import load_data, get_players, get_matches, display_mmr, maybe_create_daily_backup


st.set_page_config(
    page_title="Classement Tennis de Table",
    page_icon="🏓",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Backup quotidien automatique (au premier chargement du jour)
if "backup_done" not in st.session_state:
    maybe_create_daily_backup()
    st.session_state["backup_done"] = True

data = load_data()
players = get_players(data)
matches = get_matches(data)

# Import des pages
from pages import accueil, match, joueurs, historique, tournoi, options

# Sidebar navigation
with st.sidebar:
    st.markdown("# 🏓 Tennis de Table")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        options=[
            "🏠 Classement",
            "⚔️ Saisir un match",
            "👥 Gérer les joueurs",
            "📈 Historique",
            "🏆 Tournoi",
            "⚙️ Options",
        ],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.caption("Classement géré automatiquement\nvia un système MMR (Match Making Rating)")

# Routing
if page == "🏠 Classement":
    accueil.show()
elif page == "⚔️ Saisir un match":
    match.show()
elif page == "👥 Gérer les joueurs":
    joueurs.show()
elif page == "📈 Historique":
    historique.show()
elif page == "🏆 Tournoi":
    tournoi.show()
elif page == "⚙️ Options":
    options.show()