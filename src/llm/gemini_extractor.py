"""
Gemini Vision Extractor - Module d'extraction de relevés bancaires via Gemini Vision API.

Ce module convertit les pages PDF en images puis utilise Gemini pour extraire
les données structurées (transactions, soldes, etc.) au format JSON.
"""

import os
import json
import re
from pathlib import Path
from typing import Optional
from decimal import Decimal
from datetime import datetime

from google import genai
from google.genai import types
from pdf2image import convert_from_path
from PIL import Image
import io


class QuotaExceededError(Exception):
    """Exception levée quand le quota API Gemini est dépassé."""
    pass

# Configuration du client Gemini
def get_gemini_client() -> genai.Client:
    """Récupère le client Gemini avec la clé API."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "La clé API Gemini n'est pas configurée. "
            "Définissez la variable d'environnement GEMINI_API_KEY."
        )
    return genai.Client(api_key=api_key)

# Prompt optimisé pour l'extraction de relevés bancaires AWB
EXTRACTION_PROMPT = """Analyse ce relevé bancaire Attijariwafa Bank et extrait TOUTES les informations visibles au format JSON strictement valide.

INSTRUCTIONS IMPORTANTES:
1. Extrais TOUTES les transactions visibles, ligne par ligne
2. Les montants doivent être des nombres décimaux (utilise le point comme séparateur décimal)
3. Si un champ débit est vide, mets null. Si un champ crédit est vide, mets null.
4. La date doit être au format "JJ/MM/AAAA"
5. Le libellé doit contenir la description complète de l'opération

Retourne UNIQUEMENT le JSON suivant (pas de texte avant ou après):

{
  "banque": "Attijariwafa Bank",
  "numero_compte": "numéro du compte extrait",
  "titulaire": "nom du titulaire si visible",
  "periode": "période du relevé (ex: Janvier 2025)",
  "solde_initial": nombre_decimal_ou_null,
  "solde_final": nombre_decimal_ou_null,
  "devise": "MAD",
  "transactions": [
    {
      "date": "JJ/MM/AAAA",
      "date_valeur": "JJ/MM/AAAA ou null",
      "libelle": "description complète de l'opération",
      "debit": nombre_decimal_ou_null,
      "credit": nombre_decimal_ou_null
    }
  ]
}
"""


def pdf_to_images(pdf_path: Path, dpi: int = 200) -> list[Image.Image]:
    """
    Convertit un PDF en liste d'images PIL.
    
    Args:
        pdf_path: Chemin vers le fichier PDF
        dpi: Résolution des images (200 par défaut pour équilibrer qualité/taille)
    
    Returns:
        Liste d'images PIL
    """
    return convert_from_path(str(pdf_path), dpi=dpi)


def image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convertit une image PIL en bytes."""
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    return buffer.getvalue()


def clean_json_response(response_text: str) -> str:
    """
    Nettoie la réponse Gemini pour extraire le JSON valide.
    Gère les cas où Gemini ajoute des backticks markdown.
    """
    text = response_text.strip()
    
    # Supprimer les backticks markdown si présents
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    return text.strip()


def extract_bank_statement(
    pdf_path: Path,
    model: str = "gemini-2.0-flash",
    dpi: int = 200
) -> dict:
    """
    Extrait les données d'un relevé bancaire via Gemini Vision.
    
    Args:
        pdf_path: Chemin vers le fichier PDF
        model: Modèle Gemini à utiliser
        dpi: Résolution pour la conversion PDF → Image
    
    Returns:
        Dictionnaire contenant les données extraites:
        {
            "banque": str,
            "numero_compte": str,
            "titulaire": str,
            "periode": str,
            "solde_initial": float | None,
            "solde_final": float | None,
            "devise": str,
            "transactions": [...]
        }
    
    Raises:
        ValueError: Si la clé API n'est pas configurée
        Exception: Si l'extraction échoue
    """
    client = get_gemini_client()
    
    # Convertir le PDF en images
    images = pdf_to_images(pdf_path, dpi=dpi)
    
    # Préparer les parties du message (prompt + images)
    parts = [EXTRACTION_PROMPT]
    
    for i, img in enumerate(images):
        img_bytes = image_to_bytes(img)
        parts.append(
            types.Part.from_bytes(
                data=img_bytes,
                mime_type="image/png"
            )
        )
    
    # Appel à Gemini avec gestion des erreurs
    try:
        response = client.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Basse température pour plus de précision
                max_output_tokens=8192,
            )
        )
    except Exception as api_error:
        error_str = str(api_error)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise QuotaExceededError(
                f"Quota API épuisé pour le modèle {model}. "
                f"Essayez 'gemini-1.5-flash' ou attendez quelques minutes."
            )
        raise Exception(f"Erreur API Gemini: {error_str}")
    
    # Parser la réponse JSON
    response_text = response.text
    clean_text = clean_json_response(response_text)
    
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        raise Exception(f"Erreur de parsing JSON: {e}\nRéponse brute: {response_text}")
    
    return data


def check_api_status() -> dict:
    """
    Vérifie si l'API Gemini est correctement configurée.
    
    Returns:
        {"available": bool, "message": str}
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        return {
            "available": False,
            "message": "Clé API non configurée. Définissez GEMINI_API_KEY."
        }
    
    # Masquer la clé pour l'affichage
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    
    return {
        "available": True,
        "message": f"Clé API configurée: {masked_key}"
    }
