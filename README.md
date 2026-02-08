# Analyseur de Relevés Bancaires (AI-Powered)

Cet outil permet d'analyser, fusionner et gérer vos relevés bancaires (format PDF) en utilisant l'IA (Gemini Vision API) pour extraire les transactions avec précision.

## 🚀 Fonctionnalités

- **Extraction IA** : Utilise Google Gemini pour transformer des PDF scannés ou digitaux en données structurées.
- **Historique complet** : Sauvegarde locale dans une base de données SQLite.
- **Édition Intuitive** : Modifiez les en-têtes (banque, compte, période) et les transactions directement dans l'interface.
- **Audit de Cohérence** : Vérifie la continuité des soldes entre deux relevés successifs pour éviter les erreurs.
- **Fusion & Export** : Fusionnez plusieurs périodes en un seul "Grand Livre" et exportez au format CSV.
- **Gestion Clients** : Gérez vos clients, renommez-les ou fusionnez les comptes en un clic.

## 🛠️ Installation

1. Clonez ce repository :
   ```bash
   git clone <votre-url-github>
   cd RelevesBancaires
   ```

2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

3. Configurez votre clé API Gemini :
   Créez un fichier `.env` ou exportez la variable :
   ```bash
   export GOOGLE_API_KEY='votre_cle_ici'
   ```

4. Lancez l'application :
   ```bash
   streamlit run main.py
   ```

## 📦 Structure du Projet

- `main.py` : Point d'entrée de l'application Streamlit.
- `src/` : Code source divisé par modules (parsing, database, analyse).
- `data/` : Dossier ignoré contenant vos fichiers PDF secrets.
- `bank_data.db` : Base de données SQLite locale (ignorée par git pour sécurité).
