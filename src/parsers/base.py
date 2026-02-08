from abc import ABC, abstractmethod
from pathlib import Path
from typing import List
from ..models import ReleveBancaire

class BaseParser(ABC):
    """
    Classe abstraite définissant le contrat pour tous les parsers bancaires.
    Chaque banque (AWB, BP, CIH, etc.) aura sa propre classe héritant de celle-ci.
    """

    @abstractmethod
    def can_process(self, file_path: Path) -> bool:
        """
        Détermine si ce parser est capable de lire ce fichier spécifique.
        (ex: vérifie si le PDF contient 'Attijariwafa bank' dans l'en-tête)
        """
        pass

    @abstractmethod
    def parse(self, file_path: Path) -> ReleveBancaire:
        """
        Extrait les données du fichier et retourne un objet ReleveBancaire standardisé.
        Doit lever une exception si le parsing échoue.
        """
        pass
