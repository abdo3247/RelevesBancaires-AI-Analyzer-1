from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
import pandas as pd
from .models import ReleveBancaire, Transaction

class ConsistencyReport:
    """Rapport de cohérence entre deux relevés successifs."""
    def __init__(self, current: Dict[str, Any], next_releve: Dict[str, Any]):
        self.current_period = current['period_obj']
        self.next_period = next_releve['period_obj']
        self.current_end_balance = Decimal(str(current['solde_final']))
        self.next_start_balance = Decimal(str(next_releve['solde_initial']))
        self.is_consistent = abs(self.current_end_balance - self.next_start_balance) < Decimal('0.01')
        self.gap = self.next_start_balance - self.current_end_balance
        
        # Vérifier si les mois sont consécutifs
        self.months_diff = (self.next_period.year - self.current_period.year) * 12 + \
                          (self.next_period.month - self.current_period.month)
        self.is_consecutive = self.months_diff == 1

def parse_period(period_str: str) -> datetime:
    """Convertit 'mm-yyyy', 'MM/YYYY' ou 'Mois YYYY' en objet datetime."""
    import re
    
    # Mapping des mois français
    months_fr = {
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
        'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
    }
    
    try:
        # Format mm-yyyy (nouveau format)
        mm_yyyy_match = re.match(r'^(\d{1,2})-(\d{4})$', period_str)
        if mm_yyyy_match:
            month = int(mm_yyyy_match.group(1))
            year = int(mm_yyyy_match.group(2))
            return datetime(year, month, 1)
        
        # Format mm/yyyy
        if '/' in period_str:
            return datetime.strptime(period_str, "%m/%Y")
        
        # Format "Mois YYYY"
        parts = period_str.lower().split()
        if len(parts) >= 2 and parts[0] in months_fr:
            month = months_fr[parts[0]]
            year = int(parts[-1])
            return datetime(year, month, 1)
            
        return datetime.strptime(period_str, "%m/%Y")  # Fallback
    except:
        return datetime(2000, 1, 1)  # Date par défaut en cas d'erreur

def analyze_continuity(releves: List[Dict[str, Any]]) -> List[ConsistencyReport]:
    """
    Analyse la continuité des soldes entre une liste de relevés.
    Les relevés doivent appartenir au même compte.
    """
    # 1. Enrichir avec objet date pour tri
    enriched = []
    for r in releves:
        r_copy = r.copy()
        r_copy['period_obj'] = parse_period(r['periode'])
        enriched.append(r_copy)
    
    # 2. Trier par date
    sorted_releves = sorted(enriched, key=lambda x: x['period_obj'])
    
    reports = []
    for i in range(len(sorted_releves) - 1):
        report = ConsistencyReport(sorted_releves[i], sorted_releves[i+1])
        reports.append(report)
        
    return reports

def merge_statements(transactions_list: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Fusionne plusieurs listes de transactions en un seul DataFrame trié.
    """
    all_tx = []
    for tx_batch in transactions_list:
        all_tx.extend(tx_batch)
    
    if not all_tx:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_tx)
    
    # Conversion et tri
    try:
        df['date_obj'] = pd.to_datetime(df['date'], format='%Y-%m-%d')
        df = df.sort_values('date_obj')
        df = df.drop('date_obj', axis=1)
    except:
        pass # Si échec, on garde l'ordre tel quel
        
    return df
