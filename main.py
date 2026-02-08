"""
More ERP - Agrégateur et Analyseur de Relevés Bancaires
Interface Streamlit pour l'upload et l'analyse de relevés bancaires via Gemini Vision.
Suivi et Historique via SQLite.
"""

import pandas as pd
import streamlit as st
from pathlib import Path
from decimal import Decimal
import tempfile
import os

# Configuration de la page
st.set_page_config(
    page_title="More ERP - Analyse Bancaire",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Imports locaux
from src.parsers.awb_gemini_parser import AWBGeminiParser
import src.database as db
import src.analysis as analysis

def format_currency(amount: Decimal) -> str:
    """Formate un montant en devise (MAD)."""
    return f"{float(amount):,.2f} MAD".replace(",", " ")

def main():
    # Initialisation de la base de données
    db.init_db()

    # Header
    st.title("🚀 More ERP")
    st.subheader("Agrégateur et Analyseur de Relevés Bancaires")
    
    # --- Sidebar : Configuration ---
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # 1. Gestion de la clé API Gemini
        saved_key = db.get_api_key()
        env_key = os.environ.get("GEMINI_API_KEY", "")
        
        # Priorité : Clé en session > Clé DB > Clé Env
        current_key = st.session_state.get("gemini_api_key", saved_key or env_key)
        
        if current_key:
            os.environ["GEMINI_API_KEY"] = current_key
            st.success("✅ Clé API active")
            if st.button("🗑️ Oublier la clé"):
                db.clear_api_key()
                if "gemini_api_key" in st.session_state:
                    del st.session_state["gemini_api_key"]
                os.environ.pop("GEMINI_API_KEY", None)
                st.rerun()
        else:
            st.warning("⚠️ Clé API manquante")
            input_key = st.text_input(
                "🔑 Entrez votre clé Gemini",
                type="password",
                help="Obtenez votre clé sur https://aistudio.google.com/apikey"
            )
            if input_key:
                db.save_api_key(input_key)
                st.session_state["gemini_api_key"] = input_key
                os.environ["GEMINI_API_KEY"] = input_key
                st.rerun()
        
        # Vérifier le statut de l'API (seulement si clé présente)
        if os.environ.get("GEMINI_API_KEY"):
            status = AWBGeminiParser.is_api_available()
            if not status["available"]:
                st.error(f"❌ Erreur: {status['message']}")

        st.divider()
        
        # 2. Sélection du modèle
        model = st.selectbox(
            "🤖 Modèle Gemini",
            options=[
                "gemini-2.5-flash",
                "gemini-2.5-pro", 
                "gemini-3-flash-preview",
                "gemini-3-pro-preview"
            ],
            index=0,
            help="Gemini 2.5 Flash = rapide et stable, Gemini 3 = les plus récents (preview)"
        )
        st.session_state["gemini_model"] = model
        
        st.divider()
        st.info(f"📁 Base de données : {db.DB_PATH.absolute()}")


    # --- Onglets Principaux ---
    tab_upload, tab_history, tab_analysis, tab_clients = st.tabs([
        "📤 Import", "📜 Historique", "🕵️ Audit & Fusion", "👥 Clients & Comptes"
    ])

    with tab_upload:
        show_upload_section()

    with tab_history:
        show_history_section()

    with tab_analysis:
        show_analysis_section()

    with tab_clients:
        show_clients_section()


def show_upload_section():
    """Onglet 1 : Upload Multiple et Analyse"""
    st.header("Importation par Lots")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_files = st.file_uploader(
            "Déposez vos relevés PDF ici (plusieurs fichiers acceptés)",
            type=["pdf"],
            accept_multiple_files=True,
            help="Formats supportés: PDF (natifen ou scanné)"
        )

    with col2:
        st.markdown("**Ou depuis data/raw:**")
        data_dir = Path("data/raw")
        existing_files = list(data_dir.glob("*.pdf")) if data_dir.exists() else []
        selected_local_files = st.multiselect(
            "Fichiers locaux",
            options=[f.name for f in existing_files],
            default=[]
        )

    # Combiner les fichiers à traiter
    files_to_process = []
    
    if uploaded_files:
        for uf in uploaded_files:
            # Sauvegarder temp
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uf.read())
                files_to_process.append({"path": Path(tmp.name), "name": uf.name})
    
    if selected_local_files:
        for f_name in selected_local_files:
             files_to_process.append({"path": data_dir / f_name, "name": f_name})

    # Résumé et Action
    if files_to_process:
        st.info(f"📎 {len(files_to_process)} fichiers prêts à être analysés.")
        
        api_ready = os.environ.get("GEMINI_API_KEY", "") != ""
        if not api_ready:
            st.warning("⚠️ Configurez votre clé API d'abord.")
        
        if st.button(f"🔍 Lancer l'analyse de {len(files_to_process)} fichiers", type="primary", disabled=not api_ready):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            success_count = 0
            errors = []
            
            for i, file_info in enumerate(files_to_process):
                status_text.text(f"Traitement de {file_info['name']} ({i+1}/{len(files_to_process)})...")
                
                try:
                    process_single_file(file_info['path'])
                    success_count += 1
                except Exception as e:
                    errors.append(f"{file_info['name']}: {str(e)}")
                
                progress_bar.progress((i + 1) / len(files_to_process))
            
            status_text.text("Terminé !")
            
            if success_count > 0:
                st.success(f"✅ {success_count} fichiers traités avec succès !")
            
            if errors:
                st.error(f"❌ {len(errors)} erreurs survenues :")
                for err in errors:
                    st.write(f"- {err}")


def process_single_file(file_path: Path):
    """Traite un fichier unique et sauvegarde en silence."""
    model = st.session_state.get("gemini_model", "gemini-2.5-flash")
    parser = AWBGeminiParser(model=model)
    releve = parser.parse(file_path)
    
    if releve:
        db.save_releve(releve)
    else:
        raise Exception("Vérifiez le format du fichier.")


def show_history_section():
    """Onglet 2 : Historique avec UX amélioré"""
    st.header("📜 Historique des Relevés")
    releves = db.get_all_releves()
    
    if not releves:
        st.info("Aucun relevé importé.")
        return

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        banques = list(set(r['banque'] for r in releves))
        filter_banque = st.multiselect("Banque", banques, default=banques)
    with col_f2:
        titulaires = list(set(r['titulaire'] for r in releves))
        filter_titulaire = st.multiselect("Client", titulaires, default=titulaires)

    filtered_releves = [r for r in releves if r['banque'] in filter_banque and r['titulaire'] in filter_titulaire]

    if filtered_releves:
        # Tableau avec solde_initial ajouté
        df_display = pd.DataFrame(filtered_releves)[['date_import', 'banque', 'titulaire', 'periode', 'solde_initial', 'solde_final']]
        df_display.columns = ['Import', 'Banque', 'Titulaire', 'Période', 'Solde Début', 'Solde Fin']
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📝 Détails & Corrections")
        
        # Sélection pour édition
        selected_id = st.selectbox(
            "Choisir un relevé à modifier",
            options=[r['id'] for r in filtered_releves],
            format_func=lambda x: next((f"{r['periode']} - {r['titulaire']} ({r['banque']})" for r in filtered_releves if r['id'] == x), x)
        )
        
        if selected_id:
            releve = next(r for r in filtered_releves if r['id'] == selected_id)
            
            # --- En-tête avec Mois/Année ---
            with st.expander("✏️ Modifier l'en-tête", expanded=False):
                with st.form("edit_header"):
                    col1, col2, col3 = st.columns(3)
                    
                    new_titulaire = col1.text_input("Titulaire", releve['titulaire'])
                    new_banque = col2.text_input("Banque", releve['banque'])
                    new_compte = col3.text_input("N° Compte", releve['compte'])
                    
                    # Parsing mois/année depuis periode
                    mois_options = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                                   "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
                    periode_str = releve['periode']
                    
                    # Tenter d'extraire mois et année (supporte mm-yyyy ou "Mois Année")
                    current_mois_idx = 0
                    current_year = 2025
                    import re
                    
                    # Format mm-yyyy
                    mm_yyyy_match = re.match(r'^(\d{1,2})-(\d{4})$', periode_str)
                    if mm_yyyy_match:
                        current_mois_idx = int(mm_yyyy_match.group(1)) - 1
                        current_year = int(mm_yyyy_match.group(2))
                    else:
                        # Format "Mois Année"
                        for i, m in enumerate(mois_options):
                            if m.lower() in periode_str.lower():
                                current_mois_idx = i
                                break
                        year_match = re.search(r'(\d{4})', periode_str)
                        if year_match:
                            current_year = int(year_match.group(1))
                    
                    col_m, col_y = st.columns(2)
                    new_mois = col_m.selectbox("Mois", mois_options, index=current_mois_idx)
                    new_annee = col_y.number_input("Année", value=current_year, min_value=2000, max_value=2100, step=1)
                    
                    col_s1, col_s2 = st.columns(2)
                    new_solde_in = col_s1.number_input("Solde Initial", value=float(releve['solde_initial']))
                    new_solde_out = col_s2.number_input("Solde Final", value=float(releve['solde_final']))
                    
                    if st.form_submit_button("💾 Sauvegarder l'en-tête"):
                        # Format mm-yyyy pour tri facile
                        mois_num = mois_options.index(new_mois) + 1
                        new_periode = f"{mois_num:02d}-{int(new_annee)}"
                        db.update_releve_header(
                            selected_id, new_titulaire, new_banque, 
                            new_compte, new_solde_in, new_solde_out
                        )
                        # Mettre à jour la période aussi
                        conn = db.get_db_connection()
                        conn.execute("UPDATE releves SET periode = ? WHERE id = ?", (new_periode, selected_id))
                        conn.commit()
                        conn.close()
                        st.success("✅ En-tête mis à jour !")
                        st.rerun()

            # --- Transactions avec Solde Courant ---
            transactions = db.get_releve_transactions(selected_id)
            
            st.subheader("💳 Transactions")
            
            if transactions:
                df_trans = pd.DataFrame(transactions)
                df_edit = df_trans[['date', 'designation', 'debit', 'credit']].copy()
                df_edit['date'] = pd.to_datetime(df_edit['date'], errors='coerce')
                
                # Calculer le solde courant
                solde_initial = float(releve['solde_initial'])
                soldes = [solde_initial]
                for i, row in df_edit.iterrows():
                    nouveau_solde = soldes[-1] + float(row['credit'] or 0) - float(row['debit'] or 0)
                    soldes.append(nouveau_solde)
                df_edit['solde'] = soldes[1:]  # Enlever le solde initial de départ
                
                # Éditeur de données (solde en lecture seule)
                edited_df = st.data_editor(
                    df_edit,
                    use_container_width=True,
                    num_rows="dynamic",
                    column_config={
                        "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                        "designation": st.column_config.TextColumn("Désignation", width="large"),
                        "debit": st.column_config.NumberColumn("Débit", format="%.2f"),
                        "credit": st.column_config.NumberColumn("Crédit", format="%.2f"),
                        "solde": st.column_config.NumberColumn("Solde", format="%.2f", disabled=True)
                    },
                    column_order=["date", "designation", "debit", "credit", "solde"]
                )
                
                # Ligne de totaux
                total_debit = edited_df['debit'].sum()
                total_credit = edited_df['credit'].sum()
                solde_calcule = solde_initial + total_credit - total_debit
                
                col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                col_t1.metric("📊 Total Débits", f"{total_debit:,.2f} MAD")
                col_t2.metric("📊 Total Crédits", f"{total_credit:,.2f} MAD")
                col_t3.metric("📈 Solde Calculé", f"{solde_calcule:,.2f} MAD")
                
                # Comparaison avec solde final
                ecart = solde_calcule - float(releve['solde_final'])
                if abs(ecart) < 0.01:
                    col_t4.metric("✅ Écart", "0.00 MAD", delta="OK", delta_color="off")
                else:
                    col_t4.metric("⚠️ Écart", f"{ecart:+,.2f} MAD", delta="À vérifier", delta_color="inverse")

                # Bouton sauvegarde
                if st.button("💾 Sauvegarder les modifications"):
                    new_transactions = edited_df.to_dict('records')
                    cleaned = []
                    for t in new_transactions:
                        if t.get('date') and t.get('designation'):
                            d_val = t['date']
                            d_str = d_val.strftime("%Y-%m-%d") if hasattr(d_val, 'strftime') else str(d_val)
                            cleaned.append({
                                'date': d_str,
                                'designation': t['designation'],
                                'debit': float(t.get('debit') or 0),
                                'credit': float(t.get('credit') or 0)
                            })
                    
                    if cleaned:
                        db.replace_transactions(selected_id, cleaned)
                        st.success("✅ Transactions sauvegardées !")
                        st.rerun()
                
                # Suppression
                st.divider()
                if st.button("🗑️ Supprimer ce relevé", type="secondary"):
                    db.delete_releve(selected_id)
                    st.rerun()
                    st.rerun()


def show_analysis_section():
    """Onglet 3 : Analyse Avancée (Fusion & Cohérence)"""
    st.header("🕵️ Audit de Cohérence & Fusion")
    
    releves = db.get_all_releves()
    if not releves:
        st.warning("Importez des relevés d'abord.")
        return

    # 1. Sélectionner un compte à auditer
    accounts = list(set(f"{r['titulaire']} - {r['banque']} ({r['compte']})" for r in releves))
    selected_account = st.selectbox("Sélectionner un compte à analyser", accounts)
    
    if selected_account:
        # Filtrer les relevés de ce compte
        titulaire, rest = selected_account.split(" - ", 1)
        account_releves = [r for r in releves if r['titulaire'] == titulaire]
        
        # Analyse de continuité
        if len(account_releves) > 1:
            st.subheader("1. Cohérence des Soldes")
            
            # Enrichir avec objets date pour le tri (via parsing simple)
            reports = analysis.analyze_continuity(account_releves)
            
            for rep in reports:
                col_icon, col_det = st.columns([1, 10])
                with col_icon:
                    if rep.is_consistent:
                        st.markdown("✅")
                    else:
                        st.markdown("❌")
                
                with col_det:
                    msg = f"**{rep.current_period.strftime('%B %Y')}** (Fin: {rep.current_end_balance:,.2f}) → **{rep.next_period.strftime('%B %Y')}** (Début: {rep.next_start_balance:,.2f})"
                    st.markdown(msg)
                    if not rep.is_consistent:
                        st.error(f"⚠️ Écart de solde : {rep.gap:+,.2f} MAD")
                    if not rep.is_consecutive:
                        st.warning(f"⚠️ Attention : Mois non consécutifs ou manquants entre ces deux relevés.")
                        
        else:
            st.info("Il faut au moins 2 relevés pour analyser la continuité.")

        # Fusion et Export
        st.divider()
        st.subheader("2. Fusion & Export")
        
        # Sélection des périodes à fusionner
        st.write("**Sélectionnez les périodes à fusionner :**")
        
        # Trier les relevés par période
        sorted_releves = sorted(account_releves, key=lambda x: x['periode'])
        
        # Multi-select pour les périodes
        periode_options = {r['id']: f"{r['periode']} (Solde: {r['solde_final']:,.2f})" for r in sorted_releves}
        selected_periodes = st.multiselect(
            "Périodes",
            options=list(periode_options.keys()),
            default=list(periode_options.keys()),
            format_func=lambda x: periode_options[x]
        )
        
        if st.button("🔄 Fusionner les périodes sélectionnées"):
            if not selected_periodes:
                st.warning("Sélectionnez au moins une période.")
            else:
                all_transactions = []
                for r in sorted_releves:
                    if r['id'] in selected_periodes:
                        txs = db.get_releve_transactions(r['id'])
                        for t in txs:
                            t['periode'] = r['periode']
                        all_transactions.extend(txs)
                
                if all_transactions:
                    # Créer DataFrame propre
                    df_merged = pd.DataFrame(all_transactions)
                    
                    # Convertir et trier par date
                    df_merged['date'] = pd.to_datetime(df_merged['date'], errors='coerce')
                    df_merged = df_merged.sort_values('date')
                    
                    # Calculer le solde courant sur l'ensemble fusionné
                    first_releve = next(r for r in sorted_releves if r['id'] == selected_periodes[0])
                    solde_initial = float(first_releve['solde_initial'])
                    
                    soldes = []
                    solde = solde_initial
                    for _, row in df_merged.iterrows():
                        solde = solde + float(row['credit'] or 0) - float(row['debit'] or 0)
                        soldes.append(solde)
                    df_merged['solde'] = soldes
                    
                    # Afficher le DataFrame
                    st.dataframe(
                        df_merged[['date', 'designation', 'debit', 'credit', 'solde', 'periode']],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                            "designation": "Désignation",
                            "debit": st.column_config.NumberColumn("Débit", format="%.2f"),
                            "credit": st.column_config.NumberColumn("Crédit", format="%.2f"),
                            "solde": st.column_config.NumberColumn("Solde", format="%.2f"),
                            "periode": "Période"
                        }
                    )
                    
                    # Totaux
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total Débits", f"{df_merged['debit'].sum():,.2f} MAD")
                    col2.metric("Total Crédits", f"{df_merged['credit'].sum():,.2f} MAD")
                    col3.metric("Solde Final", f"{soldes[-1] if soldes else 0:,.2f} MAD")
                    
                    # Export CSV
                    csv_export = df_merged[['date', 'designation', 'debit', 'credit', 'solde', 'periode']].copy()
                    csv_export['date'] = csv_export['date'].dt.strftime('%d/%m/%Y')
                    csv = csv_export.to_csv(index=False, sep=";", decimal=",")
                    st.download_button(
                        "📥 Télécharger le Grand Livre (CSV)",
                        data=csv,
                        file_name=f"grand_livre_{titulaire.replace(' ', '_')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("Aucune transaction trouvée.")


def show_clients_section():
    """Onglet 4 : Gestion des Clients et Comptes"""
    st.header("👥 Gestion des Clients & Comptes")
    
    releves = db.get_all_releves()
    
    if not releves:
        st.info("Aucune donnée. Importez des relevés d'abord.")
        return
    
    # Extraire les clients uniques
    clients = {}
    for r in releves:
        titulaire = r['titulaire']
        if titulaire not in clients:
            clients[titulaire] = {
                'comptes': set(),
                'banques': set(),
                'nb_releves': 0,
                'premier_releve': r['periode'],
                'dernier_releve': r['periode']
            }
        clients[titulaire]['comptes'].add(r['compte'])
        clients[titulaire]['banques'].add(r['banque'])
        clients[titulaire]['nb_releves'] += 1
    
    # --- Vue d'ensemble ---
    st.subheader("📋 Liste des Clients")
    
    client_data = []
    for name, info in clients.items():
        client_data.append({
            'Client': name,
            'Banques': ', '.join(info['banques']),
            'Comptes': len(info['comptes']),
            'Relevés': info['nb_releves']
        })
    
    df_clients = pd.DataFrame(client_data)
    st.dataframe(df_clients, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # --- Détails d'un client ---
    st.subheader("🔍 Détails d'un Client")
    
    selected_client = st.selectbox(
        "Sélectionner un client",
        options=list(clients.keys()),
        format_func=lambda x: f"{x} ({clients[x]['nb_releves']} relevés)"
    )
    
    if selected_client:
        client_releves = [r for r in releves if r['titulaire'] == selected_client]
        
        # Comptes liés
        comptes = list(set(r['compte'] for r in client_releves))
        banques = list(set(r['banque'] for r in client_releves))
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🏦 Banques :**")
            for b in banques:
                st.write(f"  • {b}")
        
        with col2:
            st.markdown("**💳 Comptes bancaires :**")
            for c in comptes:
                st.write(f"  • `{c}`")
        
        # Historique des relevés de ce client
        st.markdown("**📅 Historique des relevés :**")
        df_hist = pd.DataFrame(client_releves)[['periode', 'banque', 'compte', 'solde_initial', 'solde_final']]
        df_hist.columns = ['Période', 'Banque', 'Compte', 'Solde Début', 'Solde Fin']
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        
        # --- Modifier le nom du client ---
        st.divider()
        st.subheader("✏️ Renommer ce client")
        
        with st.form("rename_client"):
            new_name = st.text_input("Nouveau nom", value=selected_client)
            
            if st.form_submit_button("💾 Appliquer à tous les relevés"):
                if new_name and new_name != selected_client:
                    conn = db.get_db_connection()
                    conn.execute(
                        "UPDATE releves SET titulaire = ? WHERE titulaire = ?",
                        (new_name, selected_client)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Client renommé de '{selected_client}' vers '{new_name}'")
                    st.rerun()
                else:
                    st.warning("Entrez un nom différent.")
        
        # --- Fusionner avec un autre client ---
        st.divider()
        st.subheader("🔗 Fusionner avec un autre client")
        
        other_clients = [c for c in clients.keys() if c != selected_client]
        if other_clients:
            with st.form("merge_clients"):
                target_client = st.selectbox("Fusionner vers", other_clients)
                
                if st.form_submit_button("🔀 Fusionner"):
                    conn = db.get_db_connection()
                    conn.execute(
                        "UPDATE releves SET titulaire = ? WHERE titulaire = ?",
                        (target_client, selected_client)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Tous les relevés de '{selected_client}' ont été transférés vers '{target_client}'")
                    st.rerun()
        else:
            st.info("Aucun autre client disponible pour fusion.")

if __name__ == "__main__":
    main()

