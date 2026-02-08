import sqlite3
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from .models import ReleveBancaire, Transaction

DB_PATH = Path("bank_data.db")

def get_db_connection():
    """Crée une connexion à la base de données SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Pour accéder aux colonnes par nom
    return conn

def init_db():
    """Initialise la base de données avec les tables nécessaires."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Table pour les paramètres (Clé API)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Table pour les relevés
    c.execute('''
        CREATE TABLE IF NOT EXISTS releves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            banque TEXT,
            compte TEXT,
            titulaire TEXT,
            periode TEXT,
            solde_initial REAL,
            solde_final REAL,
            date_import TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(banque, compte, periode)
        )
    ''')
    
    # Table pour les transactions
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            releve_id INTEGER,
            date TEXT,
            designation TEXT,
            debit REAL,
            credit REAL,
            FOREIGN KEY (releve_id) REFERENCES releves (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Gestion de la Clé API ---

def save_api_key(api_key: str):
    """Sauvegarde la clé API."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('gemini_api_key', api_key))
    conn.commit()
    conn.close()

def get_api_key() -> Optional[str]:
    """Récupère la clé API."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', ('gemini_api_key',))
    result = c.fetchone()
    conn.close()
    return result['value'] if result else None

def clear_api_key():
    """Supprime la clé API."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM settings WHERE key = ?', ('gemini_api_key',))
    conn.commit()
    conn.close()

# --- Gestion des Relevés ---

def save_releve(releve: ReleveBancaire) -> int:
    """
    Sauvegarde un relevé et ses transactions.
    Met à jour si le relevé existe déjà (banque + compte + période).
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # Vérifier si le relevé existe déjà
        c.execute('''
            SELECT id FROM releves 
            WHERE banque = ? AND compte = ? AND periode = ?
        ''', (releve.banque, releve.compte, releve.periode))
        
        result = c.fetchone()
        
        if result:
            releve_id = result['id']
            # Mettre à jour les infos du relevé
            c.execute('''
                UPDATE releves 
                SET titulaire = ?, solde_initial = ?, solde_final = ?, date_import = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (releve.titulaire, float(releve.solde_initial), float(releve.solde_final), releve_id))
            
            # Supprimer les anciennes transactions pour les remplacer
            c.execute('DELETE FROM transactions WHERE releve_id = ?', (releve_id,))
        else:
            # Créer un nouveau relevé
            c.execute('''
                INSERT INTO releves (banque, compte, titulaire, periode, solde_initial, solde_final)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (releve.banque, releve.compte, releve.titulaire, releve.periode, 
                  float(releve.solde_initial), float(releve.solde_final)))
            releve_id = c.lastrowid
            
        # Insérer les transactions
        for t in releve.transactions:
            c.execute('''
                INSERT INTO transactions (releve_id, date, designation, debit, credit)
                VALUES (?, ?, ?, ?, ?)
            ''', (releve_id, t.date.strftime("%Y-%m-%d"), t.designation, float(t.debit), float(t.credit)))
            
        conn.commit()
        return releve_id
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_all_releves() -> List[Dict[str, Any]]:
    """Récupère la liste sommaire de tous les relevés."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT id, banque, compte, titulaire, periode, solde_initial, solde_final, date_import,
        (SELECT COUNT(*) FROM transactions WHERE releve_id = releves.id) as nb_transactions
        FROM releves
        ORDER BY date_import DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_releve_transactions(releve_id: int) -> List[Dict[str, Any]]:
    """Récupère les transactions d'un relevé spécifique."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE releve_id = ? ORDER BY date', (releve_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_releve(releve_id: int):
    """Supprime un relevé et ses transactions."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM releves WHERE id = ?', (releve_id,))
    # Les transactions seront supprimées automatiquement grâce à ON DELETE CASCADE
    conn.commit()
    conn.close()

def update_releve_header(releve_id: int, titulaire: str, banque: str, compte: str, solde_initial: float, solde_final: float):
    """Met à jour les informations d'en-tête d'un relevé."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE releves 
        SET titulaire = ?, banque = ?, compte = ?, solde_initial = ?, solde_final = ?
        WHERE id = ?
    ''', (titulaire, banque, compte, solde_initial, solde_final, releve_id))
    conn.commit()
    conn.close()

def replace_transactions(releve_id: int, transactions: List[Dict[str, Any]]):
    """Remplace toutes les transactions d'un relevé."""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # 1. Supprimer les anciennes
        c.execute('DELETE FROM transactions WHERE releve_id = ?', (releve_id,))
        
        # 2. Insérer les nouvelles
        for t in transactions:
            c.execute('''
                INSERT INTO transactions (releve_id, date, designation, debit, credit)
                VALUES (?, ?, ?, ?, ?)
            ''', (releve_id, t['date'], t['designation'], t['debit'], t['credit']))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
