import streamlit as st
import json
import os
from datetime import datetime
from core.ranking import (
    load_data,
    save_data,
    list_available_versions,
    load_version,
    get_export_json_bytes,
    create_export,
    resimulate,
    apply_resimulation,
    DATA_FILE,
)


def show():
    st.title("⚙️ Options")
    st.markdown("Gestion des sauvegardes, exports et resimulations.")
    st.markdown("---")

    # ── Section 1 : État des sauvegardes ─────────────────────────────────────
    st.subheader("🗂️ Sauvegardes")

    versions = list_available_versions()
    backups = [v for v in versions if v["type"] == "backup"]
    exports = [v for v in versions if v["type"] == "export"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Fichier actif**")
        if os.path.exists(DATA_FILE):
            mtime = os.path.getmtime(DATA_FILE)
            modif = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y à %H:%M")
            st.success(f"players.json\n\nDernière modification : {modif}")
        else:
            st.error("Aucun fichier actif trouvé.")

    with col2:
        st.markdown("**Sauvegarde quotidienne**")
        if backups:
            st.info(backups[0]["label"])
        else:
            st.warning("Aucune sauvegarde disponible.\nElle sera créée au prochain lancement.")

    with col3:
        st.markdown("**Dernier export**")
        if exports:
            st.info(exports[0]["label"])
        else:
            st.warning("Aucun export effectué.")

    st.markdown("---")

    # ── Section 2 : Export ────────────────────────────────────────────────────
    st.subheader("📥 Exporter les données")
    st.markdown(
        "Télécharge une copie du classement actuel au format JSON. "
        "Utile pour partager les données avec le reste du club."
    )

    col_dl, col_save = st.columns([1, 1])

    with col_dl:
        json_bytes = get_export_json_bytes()
        today_str = datetime.now().strftime("%Y-%m-%d")
        if json_bytes:
            st.download_button(
                label="⬇️ Télécharger le JSON actuel",
                data=json_bytes,
                file_name=f"classement_tennis_{today_str}.json",
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.error("Impossible de lire le fichier de données.")

    with col_save:
        if st.button("💾 Créer un export daté", use_container_width=True):
            ok, result = create_export()
            if ok:
                fname = os.path.basename(result)
                st.success(f"Export créé : **{fname}**\nIl sera visible dans « Charger une version ».")
            else:
                st.error(result)

    st.markdown("---")

    # ── Section 3 : Charger une version antérieure ────────────────────────────
    st.subheader("⏪ Charger une version antérieure")
    st.markdown(
        "Remplace le classement actuel par une sauvegarde ou un export précédent. "
        "**Toutes les données ajoutées depuis cette version seront perdues.**"
    )

    if not versions:
        st.info("Aucune version antérieure disponible pour le moment.")
    else:
        options_labels = [v["label"] for v in versions]
        selected_label = st.selectbox(
            "Choisir une version à restaurer",
            options=options_labels,
            index=0,
        )
        selected_version = next(v for v in versions if v["label"] == selected_label)

        # Aperçu du fichier sélectionné
        try:
            with open(selected_version["path"], "r", encoding="utf-8") as f:
                preview_data = json.load(f)
            n_players = len([p for p in preview_data.get("players", []) if p.get("status") == "active"])
            n_matches = len(preview_data.get("matches", []))
            st.caption(f"Ce fichier contient **{n_players} joueurs actifs** et **{n_matches} matchs**.")
        except Exception:
            st.caption("Impossible de lire l'aperçu de ce fichier.")

        # Confirmation en deux étapes
        if "confirm_load" not in st.session_state:
            st.session_state["confirm_load"] = False

        if not st.session_state["confirm_load"]:
            if st.button(
                f"🔄 Restaurer « {selected_label} »",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state["confirm_load"] = True
                st.rerun()
        else:
            st.warning(
                f"⚠️ Tu es sur le point de remplacer **toutes les données actuelles** "
                f"par la version **« {selected_label} »**.\n\n"
                "Un backup du fichier actuel sera automatiquement créé avant l'opération."
            )
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ Confirmer la restauration", type="primary", use_container_width=True):
                    ok, msg = load_version(selected_version["path"])
                    st.session_state["confirm_load"] = False
                    if ok:
                        st.success(msg + " Recharge la page pour voir les changements.")
                        st.cache_data.clear()
                    else:
                        st.error(msg)
            with col_no:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state["confirm_load"] = False
                    st.rerun()

    st.markdown("---")

    # ── Section 4 : Resimulation ──────────────────────────────────────────────
    st.subheader("🔄 Resimulation")
    st.markdown(
        "Rejoue tous les événements (ajouts de joueurs + matchs) depuis le début, "
        "dans l'ordre chronologique. Utile pour appliquer une **décision rétroactive** "
        "sans modifier l'historique manuellement."
    )
    st.caption(
        "La resimulation est calculée en mémoire uniquement. "
        "Aucun fichier n'est modifié tant que tu ne cliques pas sur **Appliquer**."
    )

    if not versions:
        st.info("Aucun fichier source disponible pour la resimulation.")
    else:
        if "sim_result" not in st.session_state:
            st.session_state["sim_result"] = None
        if "sim_source_label" not in st.session_state:
            st.session_state["sim_source_label"] = None

        # Sélecteur de source uniquement si pas de résultat en attente
        if st.session_state["sim_result"] is None:
            sim_labels = [v["label"] for v in versions]
            sim_selected_label = st.selectbox(
                "Fichier source pour la resimulation",
                options=sim_labels,
                index=0,
                key="sim_select",
            )
            sim_version = next(v for v in versions if v["label"] == sim_selected_label)

            if st.button("▶️ Lancer la resimulation", use_container_width=True):
                with st.spinner("Resimulation en cours…"):
                    ok, msg, new_data = resimulate(sim_version["path"])
                st.session_state["sim_result"] = (ok, msg, new_data)
                st.session_state["sim_source_label"] = sim_selected_label
                st.rerun()

        else:
            # Résultat en attente de confirmation
            ok, msg, new_data = st.session_state["sim_result"]
            source_label = st.session_state["sim_source_label"]

            if ok:
                st.success(f"✅ {msg}")
                st.info(f"Source : **{source_label}** — résultat en attente d'application.")

                # Tableau de comparaison avant/après
                current_data = load_data()
                current_players = {
                    p["name"]: p["mmr"]
                    for p in current_data["players"]
                    if p.get("status") == "active"
                }
                new_players = {
                    p["name"]: p["mmr"]
                    for p in new_data["players"]
                    if p.get("status") == "active"
                }

                all_names = sorted(set(current_players) | set(new_players))
                diffs = []
                for name in all_names:
                    old_mmr = current_players.get(name)
                    new_mmr = new_players.get(name)
                    if old_mmr is not None and new_mmr is not None:
                        delta = int(round(new_mmr - old_mmr))
                        if delta != 0:
                            diffs.append({
                                "Joueur": name,
                                "MMR actuel": int(round(old_mmr)),
                                "MMR resimulé": int(round(new_mmr)),
                                "Δ": f"{'+' if delta > 0 else ''}{delta}",
                            })

                if diffs:
                    st.markdown("**Différences de MMR :**")
                    st.dataframe(diffs, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucune différence de MMR entre le classement actuel et la resimulation.")

                st.warning("⚠️ Le classement actuel sera remplacé si tu appliques la resimulation.")

                col_apply, col_cancel = st.columns(2)
                with col_apply:
                    if st.button("✅ Appliquer la resimulation", type="primary", use_container_width=True):
                        apply_resimulation(new_data)
                        st.session_state["sim_result"] = None
                        st.session_state["sim_source_label"] = None
                        st.success("Classement mis à jour ! Recharge la page pour voir les changements.")
                        st.cache_data.clear()
                with col_cancel:
                    if st.button("❌ Annuler", use_container_width=True):
                        st.session_state["sim_result"] = None
                        st.session_state["sim_source_label"] = None
                        st.rerun()

            else:
                st.error(msg)
                if new_data:
                    st.caption("Vérifie les noms de joueurs dans les matchs.")
                if st.button("↩️ Retour", use_container_width=True):
                    st.session_state["sim_result"] = None
                    st.session_state["sim_source_label"] = None
                    st.rerun()

show()