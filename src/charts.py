"""
Module de visualisation pour l'analyse des relevés bancaires.
Génère des graphiques Plotly interactifs.
"""

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import List, Dict, Any
from decimal import Decimal
from datetime import datetime


# Catégories et mots-clés pour la classification automatique
CATEGORIES = {
    "Virements": ["VIREMENT", "VIR", "TRANSFERT", "VERS CLIENT"],
    "Salaires": ["SALAIRE", "PAIE", "REMUNERATION"],
    "Prélèvements": ["PRELEVEMENT", "PRLV", "SEPA"],
    "Frais Bancaires": ["FRAIS", "COMMISSION", "AGIOS", "COTISATION"],
    "Loyers": ["LOYER", "BAIL"],
    "Chèques": ["CHEQUE", "CHQ"],
    "Retraits": ["RETRAIT", "GAB", "DAB"],
    "Paiements CB": ["CB ", "CARTE", "VISA", "MASTERCARD"],
}


def categorize_transaction(libelle: str) -> str:
    """Catégorise une transaction basée sur son libellé."""
    libelle_upper = libelle.upper()
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword in libelle_upper:
                return category
    return "Autres"


def prepare_transactions_df(transactions: List[Dict[str, Any]]) -> pd.DataFrame:
    """Prépare un DataFrame des transactions avec catégories."""
    if not transactions:
        return pd.DataFrame()
    
    df = pd.DataFrame(transactions)
    
    # Convertir les colonnes numériques
    if 'debit' in df.columns:
        df['debit'] = pd.to_numeric(df['debit'], errors='coerce').fillna(0)
    if 'credit' in df.columns:
        df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)
    
    # Convertir les dates
    if 'date' in df.columns:
        df['date_obj'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        df['mois'] = df['date_obj'].dt.to_period('M').astype(str)
    
    # Ajouter catégorie
    if 'designation' in df.columns:
        df['categorie'] = df['designation'].apply(categorize_transaction)
    elif 'libelle' in df.columns:
        df['categorie'] = df['libelle'].apply(categorize_transaction)
    else:
        df['categorie'] = "Autres"
    
    return df


def plot_balance_evolution(transactions: List[Dict[str, Any]], solde_initial: float = 0) -> go.Figure:
    """
    Génère un graphique d'évolution du solde.
    
    Args:
        transactions: Liste des transactions
        solde_initial: Solde de départ
        
    Returns:
        Figure Plotly
    """
    df = prepare_transactions_df(transactions)
    
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Aucune transaction", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    # Trier par date
    df = df.sort_values('date_obj')
    
    # Calculer le solde cumulé
    df['mouvement'] = df['credit'] - df['debit']
    df['solde'] = solde_initial + df['mouvement'].cumsum()
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['date_obj'],
        y=df['solde'],
        mode='lines+markers',
        name='Solde',
        line=dict(color='#2196F3', width=2),
        marker=dict(size=6),
        fill='tozeroy',
        fillcolor='rgba(33, 150, 243, 0.1)'
    ))
    
    fig.update_layout(
        title="📈 Évolution du Solde",
        xaxis_title="Date",
        yaxis_title="Solde (MAD)",
        template="plotly_white",
        hovermode="x unified",
        showlegend=False,
        height=400
    )
    
    return fig


def plot_debit_credit_bars(transactions: List[Dict[str, Any]]) -> go.Figure:
    """
    Génère un graphique barres comparant débits et crédits par mois.
    
    Args:
        transactions: Liste des transactions
        
    Returns:
        Figure Plotly
    """
    df = prepare_transactions_df(transactions)
    
    if df.empty or 'mois' not in df.columns:
        fig = go.Figure()
        fig.add_annotation(text="Aucune donnée", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    # Agréger par mois
    monthly = df.groupby('mois').agg({
        'debit': 'sum',
        'credit': 'sum'
    }).reset_index()
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=monthly['mois'],
        y=monthly['credit'],
        name='Crédits',
        marker_color='#4CAF50'
    ))
    
    fig.add_trace(go.Bar(
        x=monthly['mois'],
        y=monthly['debit'],
        name='Débits',
        marker_color='#F44336'
    ))
    
    fig.update_layout(
        title="💰 Débits vs Crédits par Mois",
        xaxis_title="Mois",
        yaxis_title="Montant (MAD)",
        barmode='group',
        template="plotly_white",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig


def plot_expense_categories(transactions: List[Dict[str, Any]]) -> go.Figure:
    """
    Génère un camembert des dépenses par catégorie.
    
    Args:
        transactions: Liste des transactions
        
    Returns:
        Figure Plotly
    """
    df = prepare_transactions_df(transactions)
    
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Aucune donnée", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    # Filtrer uniquement les débits (dépenses)
    expenses = df[df['debit'] > 0].groupby('categorie')['debit'].sum().reset_index()
    expenses.columns = ['Catégorie', 'Montant']
    expenses = expenses.sort_values('Montant', ascending=False)
    
    if expenses.empty:
        fig = go.Figure()
        fig.add_annotation(text="Aucune dépense", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    # Couleurs personnalisées
    colors = px.colors.qualitative.Set2
    
    fig = go.Figure(data=[go.Pie(
        labels=expenses['Catégorie'],
        values=expenses['Montant'],
        hole=0.4,
        marker_colors=colors,
        textposition='outside',
        textinfo='label+percent'
    )])
    
    fig.update_layout(
        title="🥧 Répartition des Dépenses par Catégorie",
        template="plotly_white",
        height=450,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2)
    )
    
    return fig


def calculate_kpis(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcule les KPIs des transactions.
    
    Args:
        transactions: Liste des transactions
        
    Returns:
        Dictionnaire des KPIs
    """
    df = prepare_transactions_df(transactions)
    
    if df.empty:
        return {
            "total_debit": 0,
            "total_credit": 0,
            "balance": 0,
            "nb_transactions": 0,
            "avg_debit": 0,
            "avg_credit": 0,
            "max_debit": 0,
            "max_credit": 0,
            "top_category": "N/A"
        }
    
    total_debit = df['debit'].sum()
    total_credit = df['credit'].sum()
    
    # Top catégorie de dépenses
    expenses_by_cat = df[df['debit'] > 0].groupby('categorie')['debit'].sum()
    top_category = expenses_by_cat.idxmax() if not expenses_by_cat.empty else "N/A"
    
    return {
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balance": round(total_credit - total_debit, 2),
        "nb_transactions": len(df),
        "avg_debit": round(df[df['debit'] > 0]['debit'].mean(), 2) if (df['debit'] > 0).any() else 0,
        "avg_credit": round(df[df['credit'] > 0]['credit'].mean(), 2) if (df['credit'] > 0).any() else 0,
        "max_debit": round(df['debit'].max(), 2),
        "max_credit": round(df['credit'].max(), 2),
        "top_category": top_category
    }
