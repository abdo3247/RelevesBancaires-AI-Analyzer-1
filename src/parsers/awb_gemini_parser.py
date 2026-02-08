"""
Generic Gemini Parser - Parser de relevés bancaires utilisant Gemini Vision.
Supporte automatiquement toutes les banques marocaines (AWB, Bank of Africa, Crédit Agricole, etc.)
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
    Parser générique pour relevés bancaires utilisant Gemini Vision API.
    
    Détecte automatiquement la banque (AWB, Bank of Africa, Crédit Agricole, etc.)
    et extrait les transactions quelle que soit la mise en page.
    """
    
    def __init__(self, model: str = "gemini-3-flash-preview"):
        """
        Initialise le parser.
        
        Args:
            model: Modèle Gemini à utiliser (défaut: gemini-3-flash-preview)
        """
        self.model = model
    
    def can_process(self, file_path: Path) -> bool:
        """
        Vérifie si le fichier peut être traité.
        Supporte PDF, PNG, JPG, JPEG.
        """
        return file_path.suffix.lower() in [".pdf", ".png", ".jpg", ".jpeg"]
    
    def parse(self, file_path: Path, status_callback=None) -> Optional[ReleveBancaire]:
        """
        Parse un relevé bancaire AWB via Gemini Vision.
        
        Args:
            file_path: Chemin vers le fichier
            status_callback: Fonction de callback pour le statut
            
        Returns:
            ReleveBancaire avec toutes les transactions extraites
        """
        try:
            # Extraction via Gemini
            data = extract_bank_statement(
                file_path=file_path, 
                model=self.model,
                status_callback=status_callback
            )
            
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
