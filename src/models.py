from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

@dataclass
class Transaction:
    date: datetime
    designation: str
    debit: Decimal
    credit: Decimal
    
    @property
    def montant_signe(self) -> Decimal:
        """Retourne le montant : négatif si débit, positif si crédit"""
        return self.credit - self.debit

    def to_dict(self):
        return {
            "date": self.date.strftime("%d/%m/%Y"),
            "designation": self.designation,
            "debit": str(self.debit).replace('.', ','),
            "credit": str(self.credit).replace('.', ',')
        }

@dataclass
class ReleveBancaire:
    banque: str
    compte: str
    titulaire: str  # Nom du titulaire du compte
    periode: str  # ex: "01/2025"
    solde_initial: Decimal
    solde_final: Decimal
    transactions: List[Transaction]
    
    @property
    def solde_calcule(self) -> Decimal:
        """Calcule le solde final théorique basé sur les transactions"""
        total_mouvements = sum(t.montant_signe for t in self.transactions)
        return self.solde_initial + total_mouvements
    
    @property
    def is_coherent(self) -> bool:
        """Vérifie si le solde calculé correspond au solde final déclaré (à 0.01 près)"""
        return abs(self.solde_calcule - self.solde_final) < Decimal('0.01')
