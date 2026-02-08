"""
Parser AWB (Attijariwafa Bank) utilisant l'OCR pour les PDFs scannés.
Hérite de BaseParser et adapte l'extraction au format OCR spécifique AWB.
"""

import re
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ..models import ReleveBancaire, Transaction
from ..ocr.ocr_engine import extract_text_from_pdf
from .base import BaseParser


class AWBOCRParser(BaseParser):
    """
    Parser pour les relevés Attijariwafa Bank au format PDF scanné.
    Utilise l'OCR (Tesseract) pour extraire le texte avant parsing.
    """
    
    def can_process(self, file_path: Path) -> bool:
        """
        Vérifie si ce parser peut traiter le fichier.
        Tente une extraction OCR sur la première page pour détecter AWB.
        """
        try:
            text = extract_text_from_pdf(file_path, first_page=1, last_page=1)
            text_lower = text.lower()
            return (
                "attijariwafa" in text_lower or
                "attijari" in text_lower or
                "releve de compte" in text_lower
            )
        except Exception:
            return False
    
    def parse(self, file_path: Path) -> ReleveBancaire:
        """
        Extrait les données du relevé bancaire AWB via OCR.
        """
        text_content = extract_text_from_pdf(file_path)
        lines = text_content.split('\n')
        
        # Données à extraire
        solde_initial = Decimal('0')
        solde_final = Decimal('0')
        transactions: List[Transaction] = []
        periode = "Inconnue"
        compte = "Non détecté"
        
        # Extraction de l'année depuis le nom de fichier (ex: Relevé_AWB_01-2025_ZPT.pdf)
        filename_year = datetime.now().year
        filename_month = 1
        match_filename = re.search(r'(\d{2})-(\d{4})', file_path.name)
        if match_filename:
            filename_month = int(match_filename.group(1))
            filename_year = int(match_filename.group(2))
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue
            
            # Extraction du numéro de compte
            # Format OCR: COMPTE: 00 0193E000000409 21210
            if compte == "Non détecté" and "COMPTE" in line_clean.upper():
                match_compte = re.search(r'COMPTE\s*:\s*([\d\sA-Z]+)', line_clean, re.IGNORECASE)
                if match_compte:
                    compte = match_compte.group(1).replace(' ', '').replace('E', '').replace('S', '5')
            
            # Extraction Solde Initial
            # Format OCR: SOLDE DEPART AU 31 12 2024 2311,61 CREDITEUR
            # Le montant est après l'année (4 chiffres) et avant CREDITEUR/DEBITEUR
            if 'SOLDE' in line_clean.upper() and 'DEPART' in line_clean.upper():
                match_solde_init = re.search(
                    r'\d{4}\s+(\d{1,3}(?:[\s]\d{3})*[,\.]\d{2})\s+(CREDITEUR|DEBITEUR)',
                    line_clean, re.IGNORECASE
                )
                if match_solde_init:
                    amount_str = self._clean_amount(match_solde_init.group(1))
                    try:
                        solde_initial = Decimal(amount_str)
                        if 'DEBITEUR' in match_solde_init.group(2).upper():
                            solde_initial = -solde_initial
                    except:
                        pass
                    continue
            
            # Extraction Solde Final
            # Format OCR: FINAL AU 31 01 2025 102 773,14 CREDITEUR
            if 'FINAL' in line_clean.upper():
                match_solde_fin = re.search(
                    r'\d{4}\s+(\d{1,3}(?:[\s]\d{3})*[,\.]\d{2})\s+(CREDITEUR|DEBITEUR)',
                    line_clean, re.IGNORECASE
                )
                if match_solde_fin:
                    amount_str = self._clean_amount(match_solde_fin.group(1))
                    try:
                        solde_final = Decimal(amount_str)
                        if 'DEBITEUR' in match_solde_fin.group(2).upper():
                            solde_final = -solde_final
                    except:
                        pass
                    continue
            
            # Ignorer les lignes non pertinentes
            skip_patterns = [
                'TOTAL MOUVEMENTS', 'PAGE', '---', 'LIBELLE', 'VALEUR',
                'CAPITAUX', 'CREDIT', 'DATE', 'Attijariwafa', 'CamScanner',
                'société anonyme', 'capital', 'Siège', 'arrêté'
            ]
            if any(p.lower() in line_clean.lower() for p in skip_patterns):
                continue
            
            # Extraction Transactions
            # Format OCR: 0016BK/06 01] VIR.WEB RECU DE EL MRABET 07 01 2025 2 800,00
            # Pattern: CODE/JJ MM] LIBELLE JJ MM AAAA MONTANT
            transaction = self._parse_transaction_line(line_clean, filename_year, filename_month)
            if transaction:
                transactions.append(transaction)
        
        # Déduction de la période depuis le nom de fichier
        if filename_month and filename_year:
            periode = f"{filename_month:02d}/{filename_year}"
        elif transactions:
            periode = transactions[0].date.strftime("%m/%Y")
        
        return ReleveBancaire(
            banque="Attijariwafa Bank",
            compte=compte,
            periode=periode,
            solde_initial=solde_initial,
            solde_final=solde_final,
            transactions=transactions
        )
    
    def _parse_transaction_line(self, line: str, default_year: int, default_month: int) -> Optional[Transaction]:
        """
        Parse une ligne de transaction AWB.
        
        Formats détectés dans l'OCR:
        - 0016BK/06 01] VIR.WEB RECU DE EL MRABET 07 01 2025 2 800,00
        - 0016CW/06 01] FRAIS POUR CERTIFICATION CHEQUES {31 12 2024 33,00
        """
        # Pattern: Code/JJ MM] Libellé DateValeurJJ MM AAAA Montant(s)
        # Le ] peut être ] ou } ou | selon l'OCR
        pattern = re.compile(
            r'^\s*[\dO]+[A-Z]{0,3}[/\|](\d{1,2})\s+(\d{1,2})[\]\}\|]\s*'  # Code/JJ MM]
            r'(.+?)\s+'  # Libellé
            r'[\[\{\|]?(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s*'  # [JJ MM AAAA date valeur
            r'(\d+[\s\d]*[,\.]\d{2})?\s*'  # Montant 1 (débit ou crédit)
            r'(\d+[\s\d]*[,\.]\d{2})?'   # Montant 2 (optionnel)
        )
        
        match = pattern.match(line)
        if not match:
            # Pattern alternatif simplifié pour lignes avec un seul montant
            alt_pattern = re.compile(
                r'.*?(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s+'  # Date JJ MM AAAA
                r'(\d+[\s\d]*[,\.]\d{2})\s*'  # Montant
            )
            alt_match = alt_pattern.search(line)
            if alt_match:
                # Extraire le libellé de tout ce qui précède la date
                pre_date = line[:alt_match.start(1)].strip()
                # Nettoyer le libellé (supprimer le code au début)
                libelle = re.sub(r'^[\dO]+[A-Z]{0,3}[/\|]\d+\s+\d+[\]\}\|]\s*', '', pre_date).strip()
                if not libelle:
                    return None
                
                day = alt_match.group(1).zfill(2)
                month = alt_match.group(2).zfill(2)
                year = int(alt_match.group(3))
                amount_str = self._clean_amount(alt_match.group(4))
                
                try:
                    date_obj = datetime.strptime(f"{day}/{month}/{year}", "%d/%m/%Y")
                    amount = Decimal(amount_str)
                    
                    # Déterminer si c'est un débit ou crédit basé sur des mots-clés
                    libelle_upper = libelle.upper()
                    is_debit = any(kw in libelle_upper for kw in [
                        'FRAIS', 'PRELEVEMENT', 'TIMBRE', 'PAIEMENT', 
                        'RETRAIT', 'COMMISSION', 'VIREMENT EMIS'
                    ])
                    
                    return Transaction(
                        date=date_obj,
                        designation=libelle,
                        debit=amount if is_debit else Decimal('0'),
                        credit=Decimal('0') if is_debit else amount
                    )
                except (ValueError, Exception):
                    return None
            return None
        
        # Pattern principal correspondant
        op_day = match.group(1).zfill(2)
        op_month = match.group(2).zfill(2)
        libelle = match.group(3).strip()
        val_day = match.group(4).zfill(2)
        val_month = match.group(5).zfill(2)
        val_year = int(match.group(6))
        amount1_str = match.group(7)
        amount2_str = match.group(8)
        
        # Date de l'opération (utiliser date valeur)
        try:
            date_obj = datetime.strptime(f"{val_day}/{val_month}/{val_year}", "%d/%m/%Y")
        except ValueError:
            return None
        
        # Montants
        debit = Decimal('0')
        credit = Decimal('0')
        
        # Logique: si 2 montants, le premier est débit, le second crédit
        # Si 1 seul montant, déduire selon le libellé
        if amount1_str and amount2_str:
            debit = Decimal(self._clean_amount(amount1_str))
            credit = Decimal(self._clean_amount(amount2_str))
        elif amount1_str:
            amount = Decimal(self._clean_amount(amount1_str))
            libelle_upper = libelle.upper()
            is_debit = any(kw in libelle_upper for kw in [
                'FRAIS', 'PRELEVEMENT', 'TIMBRE', 'PAIEMENT', 
                'RETRAIT', 'COMMISSION', 'VIREMENT EMIS', 'CNSS'
            ])
            if is_debit:
                debit = amount
            else:
                credit = amount
        
        if debit == 0 and credit == 0:
            return None
        
        return Transaction(
            date=date_obj,
            designation=libelle,
            debit=debit,
            credit=credit
        )
    
    def _clean_amount(self, amount_str: str) -> str:
        """
        Nettoie une chaîne de montant pour la conversion en Decimal.
        """
        if not amount_str:
            return '0'
        # Supprimer les espaces
        cleaned = amount_str.replace(' ', '')
        # Remplacer la virgule par un point
        cleaned = cleaned.replace(',', '.')
        # Si plusieurs points, garder seulement le dernier
        parts = cleaned.split('.')
        if len(parts) > 2:
            cleaned = ''.join(parts[:-1]) + '.' + parts[-1]
        return cleaned
