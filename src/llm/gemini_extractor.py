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

# Prompt générique pour l'extraction de relevés bancaires (toutes banques)
EXTRACTION_PROMPT = """Analyse ce relevé bancaire et extrait TOUTES les informations visibles au format JSON strictement valide.

INSTRUCTIONS IMPORTANTES:
1. IDENTIFIE automatiquement la banque (Attijariwafa Bank, Bank of Africa, Crédit Agricole du Maroc, CIH, BMCE, etc.)
2. Extrais TOUTES les transactions visibles, ligne par ligne
3. Les montants doivent être des nombres décimaux (utilise le point comme séparateur décimal)
4. Si un champ débit est vide, mets null. Si un champ crédit est vide, mets null.
5. La date doit être au format "JJ/MM/AAAA"
6. Le libellé doit contenir la description complète de l'opération

Retourne UNIQUEMENT le JSON suivant (pas de texte avant ou après):

{
  "banque": "Nom exact de la banque détecté sur le document",
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
    file_path: Optional[Path] = None,
    file_bytes: Optional[bytes] = None,
    file_name: str = "",
    model: str = "gemini-3-flash-preview",
    dpi: int = 200,
    status_callback=None
) -> dict:
    """
    Extrait les données d'un relevé bancaire via Gemini Vision.
    Supporte PDF et Images (PNG, JPG).
    """
    client = get_gemini_client()
    
    parts = [EXTRACTION_PROMPT]
    
    # Déterminer le type de fichier
    extension = ""
    if file_path:
        extension = file_path.suffix.lower()
    elif file_name:
        extension = Path(file_name).suffix.lower()
        
    if extension == ".pdf":
        if status_callback: status_callback("Converting PDF to images...")
        if file_path:
            images = pdf_to_images(file_path, dpi=dpi)
        else:
            # Handle bytes if needed, but for now we usually have files
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)
            images = pdf_to_images(tmp_path, dpi=dpi)
            os.unlink(tmp_path)
            
        for i, img in enumerate(images):
            if status_callback: status_callback(f"Preparing page {i+1}...")
            img_bytes = image_to_bytes(img)
            parts.append(
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/png"
                )
            )
    elif extension in [".png", ".jpg", ".jpeg"]:
        if status_callback: status_callback("Processing image...")
        if file_path:
            with open(file_path, "rb") as f:
                img_data = f.read()
        else:
            img_data = file_bytes
            
        mime = "image/png" if extension == ".png" else "image/jpeg"
        parts.append(
            types.Part.from_bytes(
                data=img_data,
                mime_type=mime
            )
        )
    else:
        raise ValueError(f"Format non supporté : {extension}")

    # Appel à Gemini
    if status_callback: status_callback(f"Gemini analysis ({model})...")
    try:
        response = client.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=32768,  # Max pour les relevés multi-pages volumineux
            )
        )
    except Exception as api_error:
        error_str = str(api_error)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise QuotaExceededError(
                f"Quota API épuisé pour le modèle {model}."
            )
        raise Exception(f"Erreur API Gemini: {error_str}")
    
    # Parser la réponse
    response_text = response.text
    if not response_text:
        raise Exception("Gemini a renvoyé une réponse vide.")
    
    # Vérifier si la réponse est du texte valide (pas des données binaires)
    # Gemini peut parfois retourner des bytes nuls
    if response_text.startswith('\x00') or all(c == '0' for c in response_text[:100] if c.isalnum()):
        raise Exception(
            f"Gemini a retourné des données binaires invalides au lieu de JSON. "
            f"Essayez un autre modèle ou vérifiez que le fichier est lisible."
        )
    
    # Vérifier si la réponse a été tronquée
    finish_reason = None
    if response.candidates and len(response.candidates) > 0:
        finish_reason = response.candidates[0].finish_reason
        
    clean_text = clean_json_response(response_text)
    
    # Tenter de réparer un JSON tronqué
    if not clean_text.rstrip().endswith("}"):
        # La réponse est probablement tronquée, essayer de fermer le JSON
        clean_text = clean_text.rstrip()
        # Compter les accolades ouvertes
        open_braces = clean_text.count("{") - clean_text.count("}")
        open_brackets = clean_text.count("[") - clean_text.count("]")
        # Fermer les structures ouvertes
        clean_text += "]" * open_brackets + "}" * open_braces
    
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        # Afficher une portion plus courte de la réponse pour le debug
        preview = response_text[:500] + "..." if len(response_text) > 500 else response_text
        raise Exception(f"Erreur de parsing JSON (réponse potentiellement tronquée): {e}\nAperçu: {preview}")
    
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
