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
import src.charts as charts

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
                "gemini-3-flash-preview",
                "gemini-3-pro-preview",
                "gemini-2.5-flash",
                "gemini-2.5-pro"
            ],
            index=0,
            help="Gemini 3 Flash = le plus récent et rapide, Gemini 2.5 = stable"
        )
        st.session_state["gemini_model"] = model
        
        st.divider()
        st.info(f"📁 Base de données : {db.DB_PATH.absolute()}")


    # --- Onglets Principaux ---
    tab_upload, tab_history, tab_analysis, tab_stats, tab_clients = st.tabs([
        "📤 Import", "📜 Historique", "🕵️ Audit & Fusion", "📊 Statistiques", "👥 Clients & Comptes"
    ])

    with tab_upload:
        show_upload_section()

    with tab_history:
        show_history_section()

    with tab_analysis:
        show_analysis_section()

    with tab_stats:
        show_statistics_section()

    with tab_clients:
        show_clients_section()


def show_upload_section():
    """Onglet 1 : Upload Multiple et Analyse"""
    st.header("Importation par Lots")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_files = st.file_uploader(
            "Déposez vos relevés ici (PDF, PNG, JPG)",
            type=["pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            help="Formats supportés: PDF, PNG, JPEG. Taille max: 50 Mo par fichier."
        )

    with col2:
        st.markdown("**Ou depuis data/raw:**")
        data_dir = Path("data/raw")
        # Support multiples extensions et sous-dossiers (AWB, Bank of Africa, Crédit Agricole...)
        existing_files = []
        if data_dir.exists():
            for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
                # Recherche récursive dans tous les sous-dossiers
                existing_files.extend(list(data_dir.glob(f"**/*{ext}")))
        
        # Afficher avec le nom du dossier parent (banque)
        file_options = {}
        for f in existing_files:
            bank_folder = f.parent.name if f.parent != data_dir else "Autres"
            display_name = f"{bank_folder} / {f.name}"
            file_options[display_name] = f
        
        selected_display_names = st.multiselect(
            "Fichiers locaux",
            options=sorted(file_options.keys()),
            default=[]
        )
        # Convertir les noms affichés en chemins réels
        selected_local_files = [file_options[name].name for name in selected_display_names]
        selected_local_paths = [file_options[name] for name in selected_display_names]

    # Combiner les fichiers à traiter
    files_to_process = []
    MAX_SIZE_MB = 50
    
    if uploaded_files:
        for uf in uploaded_files:
            # Vérifier la taille (20 Mo)
            if uf.size > MAX_SIZE_MB * 1024 * 1024:
                st.error(f"❌ {uf.name} est trop volumineux (> {MAX_SIZE_MB} Mo).")
                continue
                
            # Sauvegarder temp avec la bonne extension
            ext = Path(uf.name).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(uf.read())
                files_to_process.append({"path": Path(tmp.name), "name": uf.name})
    
    if selected_display_names:
        for display_name in selected_display_names:
            full_path = file_options[display_name]
            files_to_process.append({"path": full_path, "name": full_path.name})

    # Résumé et Action
    if files_to_process:
        st.info(f"📎 {len(files_to_process)} fichiers prêts à être analysés.")
        
        api_ready = os.environ.get("GEMINI_API_KEY", "") != ""
        if not api_ready:
            st.warning("⚠️ Configurez votre clé API d'abord.")
        
        if st.button(f"🔍 Lancer l'analyse de {len(files_to_process)} fichiers", type="primary", disabled=not api_ready):
            progress_bar = st.progress(0)
            
            success_count = 0
            errors = []
            
            for i, file_info in enumerate(files_to_process):
                # Utilisation de st.status pour une meilleure UX de progression
                with st.status(f"Analyse de {file_info['name']} ({i+1}/{len(files_to_process)})...", expanded=True) as status:
                    try:
                        # Wrapper pour le callback : status.update attend des kwargs, pas un argument positionnel
                        def update_status(msg):
                            status.update(label=msg)
                        
                        process_single_file(file_info['path'], update_status)
                        success_count += 1
                        status.update(label=f"✅ {file_info['name']} terminé !", state="complete", expanded=False)
                    except Exception as e:
                        errors.append(f"{file_info['name']}: {str(e)}")
                        status.update(label=f"❌ Erreur sur {file_info['name']}", state="error", expanded=True)
                        st.error(f"Erreur Gemini: {str(e)}")

                
                progress_bar.progress((i + 1) / len(files_to_process))
            
            if success_count > 0:
                st.success(f"✅ {success_count} fichiers traités avec succès !")
            
            if errors:
                st.error(f"❌ {len(errors)} erreurs survenues.")
                for err in errors:
                    st.write(f"- {err}")


def process_single_file(file_path: Path, status_callback=None):
    """Traite un fichier unique et sauvegarde en silence."""
    model = st.session_state.get("gemini_model", "gemini-3-flash-preview")
    parser = AWBGeminiParser(model=model)
    releve = parser.parse(file_path, status_callback=status_callback)
    
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


def show_statistics_section():
    """Onglet 5 : Statistiques et Graphiques"""
    st.header("📊 Statistiques et Analyses")
    
    # Récupérer tous les relevés
    all_releves = db.get_all_releves()
    
    if not all_releves:
        st.info("📭 Aucun relevé disponible. Importez des fichiers d'abord.")
        return
    
    # Extraire années et mois des périodes
    from src.analysis import parse_period
    for r in all_releves:
        period_obj = parse_period(r['periode'])
        r['annee'] = period_obj.year
        r['mois'] = period_obj.month
    
    # --- FILTRES EN CASCADE ---
    st.subheader("🔍 Filtres")
    
    # Ligne 1 : Client et Banque
    col1, col2 = st.columns(2)
    
    with col1:
        # Liste des clients
        all_clients = sorted(list(set(r['titulaire'] for r in all_releves if r['titulaire'])))
        selected_clients = st.multiselect(
            "👤 Clients",
            options=all_clients,
            default=[],
            placeholder="Tous les clients"
        )
    
    # Filtrer pour obtenir les banques disponibles selon les clients sélectionnés
    releves_after_client = all_releves
    if selected_clients:
        releves_after_client = [r for r in all_releves if r['titulaire'] in selected_clients]
    
    with col2:
        # Banques disponibles (filtrées par client si sélectionné)
        available_banks = sorted(list(set(r['banque'] for r in releves_after_client if r['banque'])))
        selected_banks = st.multiselect(
            "🏦 Banques",
            options=available_banks,
            default=[],
            placeholder="Toutes les banques"
        )
    
    # Filtrer pour obtenir les comptes disponibles
    releves_after_bank = releves_after_client
    if selected_banks:
        releves_after_bank = [r for r in releves_after_client if r['banque'] in selected_banks]
    
    # Ligne 2 : Compte, Année, Mois
    col3, col4, col5 = st.columns(3)
    
    with col3:
        # Comptes disponibles (filtrés par client et banque)
        available_accounts = sorted(list(set(r['compte'] for r in releves_after_bank if r['compte'])))
        selected_accounts = st.multiselect(
            "💳 Comptes",
            options=available_accounts,
            default=[],
            placeholder="Tous les comptes"
        )
    
    # Filtrer pour obtenir les années disponibles
    releves_after_account = releves_after_bank
    if selected_accounts:
        releves_after_account = [r for r in releves_after_bank if r['compte'] in selected_accounts]
    
    with col4:
        # Années disponibles
        available_years = sorted(list(set(r['annee'] for r in releves_after_account)))
        selected_years = st.multiselect(
            "📅 Années",
            options=available_years,
            default=[],
            placeholder="Toutes les années"
        )
    
    # Filtrer pour obtenir les mois disponibles
    releves_after_year = releves_after_account
    if selected_years:
        releves_after_year = [r for r in releves_after_account if r['annee'] in selected_years]
    
    with col5:
        # Mois disponibles
        month_names = {1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
                       7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"}
        available_months = sorted(list(set(r['mois'] for r in releves_after_year)))
        month_options = {month_names[m]: m for m in available_months}
        selected_month_names = st.multiselect(
            "🗓️ Mois",
            options=list(month_options.keys()),
            default=[],
            placeholder="Tous les mois"
        )
        selected_months = [month_options[name] for name in selected_month_names]
    
    # --- APPLIQUER TOUS LES FILTRES ---
    filtered_releves = all_releves
    
    if selected_clients:
        filtered_releves = [r for r in filtered_releves if r['titulaire'] in selected_clients]
    if selected_banks:
        filtered_releves = [r for r in filtered_releves if r['banque'] in selected_banks]
    if selected_accounts:
        filtered_releves = [r for r in filtered_releves if r['compte'] in selected_accounts]
    if selected_years:
        filtered_releves = [r for r in filtered_releves if r['annee'] in selected_years]
    if selected_months:
        filtered_releves = [r for r in filtered_releves if r['mois'] in selected_months]
    
    # Afficher le résumé des filtres
    nb_releves = len(filtered_releves)
    st.info(f"📋 **{nb_releves}** relevé(s) sélectionné(s)")
    
    if not filtered_releves:
        st.warning("Aucun relevé pour cette sélection. Modifiez les filtres.")
        return
    
    # Récupérer toutes les transactions des relevés filtrés
    all_transactions = []
    total_solde_initial = 0
    
    for releve in filtered_releves:
        releve_id = releve['id']
        transactions = db.get_releve_transactions(releve_id)
        all_transactions.extend(transactions)
        if releve.get('solde_initial'):
            total_solde_initial = releve['solde_initial']
    
    if not all_transactions:
        st.warning("Aucune transaction dans les relevés sélectionnés.")
        return
    
    st.divider()
    
    # --- KPIs ---
    st.subheader("📈 Indicateurs Clés")
    kpis = charts.calculate_kpis(all_transactions)
    
    kpi_cols = st.columns(4)
    
    with kpi_cols[0]:
        st.metric(
            label="💰 Total Crédits",
            value=f"{kpis['total_credit']:,.2f} MAD".replace(",", " "),
            delta=f"+{kpis['nb_transactions']} transactions"
        )
    
    with kpi_cols[1]:
        st.metric(
            label="💸 Total Débits",
            value=f"{kpis['total_debit']:,.2f} MAD".replace(",", " "),
            delta=f"Moy: {kpis['avg_debit']:,.0f} MAD"
        )
    
    with kpi_cols[2]:
        balance_color = "normal" if kpis['balance'] >= 0 else "inverse"
        st.metric(
            label="📊 Balance Nette",
            value=f"{kpis['balance']:,.2f} MAD".replace(",", " "),
            delta_color=balance_color
        )
    
    with kpi_cols[3]:
        st.metric(
            label="🏆 Top Catégorie",
            value=kpis['top_category'],
            delta=f"Max débit: {kpis['max_debit']:,.0f} MAD"
        )
    
    st.divider()
    
    # --- Graphiques ---
    st.subheader("📉 Visualisations")
    
    # Graphique 1 : Évolution du solde
    fig_balance = charts.plot_balance_evolution(all_transactions, total_solde_initial)
    st.plotly_chart(fig_balance, use_container_width=True)
    
    # Deux graphiques côte à côte
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        # Graphique 2 : Débits vs Crédits
        fig_bars = charts.plot_debit_credit_bars(all_transactions)
        st.plotly_chart(fig_bars, use_container_width=True)
    
    with chart_col2:
        # Graphique 3 : Catégories de dépenses
        fig_pie = charts.plot_expense_categories(all_transactions)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    # --- Tableau des transactions par catégorie ---
    st.divider()
    st.subheader("📋 Détail par Catégorie")
    
    df = charts.prepare_transactions_df(all_transactions)
    if not df.empty and 'categorie' in df.columns:
        category_summary = df.groupby('categorie').agg({
            'debit': 'sum',
            'credit': 'sum'
        }).reset_index()
        category_summary['total'] = category_summary['credit'] - category_summary['debit']
        category_summary.columns = ['Catégorie', 'Débits', 'Crédits', 'Balance']
        category_summary = category_summary.sort_values('Débits', ascending=False)
        
        st.dataframe(
            category_summary.style.format({
                'Débits': '{:,.2f}',
                'Crédits': '{:,.2f}',
                'Balance': '{:,.2f}'
            }),
            use_container_width=True,
            hide_index=True
        )


if __name__ == "__main__":
    main()

