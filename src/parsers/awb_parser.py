import pdfplumber
import re
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from ..models import ReleveBancaire, Transaction
from .base import BaseParser

class AWBParser(BaseParser):
    def can_process(self, file_path: Path) -> bool:
        try:
            with pdfplumber.open(file_path) as pdf:
                first_page = pdf.pages[0].extract_text()
                # On cherche des mots clés typiques d'AWB
                return "Attijariwafa bank" in first_page or "RELEVE DE COMPTE BANCAIRE" in first_page
        except:
            return False

    def parse(self, file_path: Path) -> ReleveBancaire:
        with pdfplumber.open(file_path) as pdf:
            text_content = ""
            for page in pdf.pages:
                text_content += page.extract_text() + "\n"

        lines = text_content.split('\n')
        
        # Données à extraire
        solde_initial = Decimal('0')
        solde_final = Decimal('0')
        transactions: List[Transaction] = []
        periode = "Inconnue"
        
        # Extraction du contexte (Année, Mois) depuis le nom de fichier ou le contenu
        # On essaie de deviner l'année courante via le nom de fichier si possible
        filename_year = datetime.now().year
        match_filename = re.search(r'(\d{4})', file_path.name)
        if match_filename:
            filename_year = int(match_filename.group(1))

        # Regex patterns
        # Format montant français: 1 200,00 ou 1200,00 -> on doit gérer les espaces
        # Pattern pour détecter une ligne de transaction AWB typique:
        # Date | Date Valeur | Libellé | Débit | Crédit
        # Parfois: Date | Libellé | Date Valeur | Débit | Crédit
        # Simplification: On cherche une date au début, et des montants à la fin
        
        re_solde_init = re.compile(r'SOLDE (?:DEPART|INITIAL|PRECEDENT).*?(\d[\d\s]*,\d{2})\s*(DEBITEUR|CREDITEUR|D|C)?', re.IGNORECASE)
        re_solde_fin = re.compile(r'SOLDE (?:FINAL|NOUVEAU).*?(\d[\d\s]*,\d{2})\s*(DEBITEUR|CREDITEUR|D|C)?', re.IGNORECASE)
        
        # Pattern transaction: Date (JJ/MM/AAAA ou JJ/MM) ... Montant ...
        # Ex: 01/01 2025 ARRETE COMPTE ... 110,79
        re_transaction = re.compile(r'^\s*(\d{2}/\d{2})(?:/(\d{2,4}))?\s+(.*?)\s+(\d[\d\s]*,\d{2})?\s*(\d[\d\s]*,\d{2})?\s*$')

        for line in lines:
            line_clean = line.strip()
            
            # Recherche Soldes
            match_init = re_solde_init.search(line_clean)
            if match_init:
                amount_str = match_init.group(1).replace(' ', '').replace(',', '.')
                solde_initial = Decimal(amount_str)
                # Si c'est marqué DEBITEUR, c'est négatif (du point de vue banque ? Non, relevé client: Crédit = argent dispo)
                # AWB: Créditeur = positif, Débiteur = négatif
                if match_init.group(2) and 'DEB' in match_init.group(2).upper():
                    solde_initial = -solde_initial
                continue

            match_fin = re_solde_fin.search(line_clean)
            if match_fin:
                amount_str = match_fin.group(1).replace(' ', '').replace(',', '.')
                solde_final = Decimal(amount_str)
                if match_fin.group(2) and 'DEB' in match_fin.group(2).upper():
                    solde_final = -solde_final
                continue

            # Recherche Transactions
            # On ignore les lignes d'entête ou de totaux
            if "TOTAL MOUVEMENTS" in line_clean or "ANCIEN SOLDE" in line_clean or "DATE" in line_clean:
                continue

            match_trans = re_transaction.match(line_clean)
            if match_trans:
                day_month = match_trans.group(1)
                year_str = match_trans.group(2)
                description = match_trans.group(3).strip()
                debit_str = match_trans.group(4)
                credit_str = match_trans.group(5)

                # Si pas de montant détecté, c'est peut-être une ligne de suite de libellé (on ignore pour l'instant)
                if not debit_str and not credit_str:
                    continue

                # Gestion de la date
                if year_str:
                    year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)
                else:
                    year = filename_year # Fallback
                
                try:
                    date_obj = datetime.strptime(f"{day_month}/{year}", "%d/%m/%Y")
                except ValueError:
                    continue # Date invalide

                # Nettoyage des montants
                debit = Decimal('0')
                credit = Decimal('0')

                if debit_str:
                    debit = Decimal(debit_str.replace(' ', '').replace(',', '.'))
                if credit_str:
                    credit = Decimal(credit_str.replace(' ', '').replace(',', '.'))

                # On ignore les lignes où tout est zéro (rare)
                if debit == 0 and credit == 0:
                    continue

                t = Transaction(
                    date=date_obj,
                    designation=description,
                    debit=debit,
                    credit=credit
                )
                transactions.append(t)

        # Déduction de la période basée sur la première transaction
        if transactions:
            periode = transactions[0].date.strftime("%m/%Y")

        return ReleveBancaire(
            banque="Attijariwafa Bank",
            compte="ZPT", # A améliorer : extraction regex du compte
            periode=periode,
            solde_initial=solde_initial,
            solde_final=solde_final,
            transactions=transactions
        )
