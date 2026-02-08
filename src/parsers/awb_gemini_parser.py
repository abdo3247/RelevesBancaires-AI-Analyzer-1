"""
AWB Gemini Parser - Parser de relevés Attijariwafa Bank utilisant Gemini Vision.
"""

from pathlib import Path
from decimal import Decimal
from datetime import datetime
from typing import Optional

from ..models import ReleveBancaire, Transaction
from ..llm.gemini_extractor import extract_bank_statement, check_api_status
from .base import BaseParser


class AWBGeminiParser(BaseParser):
    """
    Parser pour les relevés Attijariwafa Bank utilisant Gemini Vision API.
    
    Avantages par rapport à l'OCR:
    - Compréhension contextuelle du document
    - Extraction structurée native (JSON)
    - Meilleure gestion des tableaux et formats variés
    """
    
    def __init__(self, model: str = "gemini-2.0-flash"):
        """
        Initialise le parser.
        
        Args:
            model: Modèle Gemini à utiliser (défaut: gemini-2.0-flash)
        """
        self.model = model
    
    def can_process(self, file_path: Path) -> bool:
        """
        Vérifie si le fichier peut être traité.
        
        Pour l'instant, on accepte tous les PDF. Une amélioration future
        pourrait détecter spécifiquement les relevés AWB.
        """
        return file_path.suffix.lower() == ".pdf"
    
    def parse(self, file_path: Path) -> Optional[ReleveBancaire]:
        """
        Parse un relevé bancaire AWB via Gemini Vision.
        
        Args:
            file_path: Chemin vers le fichier PDF
            
        Returns:
            ReleveBancaire avec toutes les transactions extraites,
            ou None si l'extraction échoue
        """
        try:
            # Extraction via Gemini
            data = extract_bank_statement(file_path, model=self.model)
            
            # Conversion en objets du modèle
            transactions = []
            for t in data.get("transactions", []):
                try:
                    # Parser la date
                    date_str = t.get("date", "")
                    if date_str:
                        date = datetime.strptime(date_str, "%d/%m/%Y")
                    else:
                        continue  # Skip transactions sans date
                    
                    # Parser les montants
                    debit = Decimal(str(t.get("debit") or 0))
                    credit = Decimal(str(t.get("credit") or 0))
                    
                    transaction = Transaction(
                        date=date,
                        designation=t.get("libelle", ""),
                        debit=debit,
                        credit=credit
                    )
                    transactions.append(transaction)
                    
                except (ValueError, TypeError) as e:
                    # Log l'erreur mais continue avec les autres transactions
                    print(f"Erreur parsing transaction: {t} - {e}")
                    continue
            
            # Créer le relevé bancaire
            releve = ReleveBancaire(
                banque=data.get("banque", "Attijariwafa Bank"),
                compte=data.get("numero_compte", ""),
                titulaire=data.get("titulaire", "Inconnu"),
                periode=data.get("periode", ""),
                solde_initial=Decimal(str(data.get("solde_initial") or 0)),
                solde_final=Decimal(str(data.get("solde_final") or 0)),
                transactions=transactions
            )
            
            return releve
            
        except Exception as e:
            print(f"Erreur lors de l'extraction Gemini: {e}")
            raise  # Re-raise pour que le message d'erreur soit visible dans l'UI
    
    @staticmethod
    def is_api_available() -> dict:
        """
        Vérifie si l'API Gemini est disponible.
        
        Returns:
            {"available": bool, "message": str}
        """
        return check_api_status()
