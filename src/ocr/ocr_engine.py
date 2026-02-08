"""
Module OCR pour l'extraction de texte à partir de PDFs scannés.
Utilise Tesseract via pytesseract et pdf2image pour la conversion PDF→Image.
"""

from pathlib import Path
from typing import Optional
import pytesseract
from pdf2image import convert_from_path
from PIL import Image


def extract_text_from_pdf(
    pdf_path: Path | str,
    lang: str = "fra+eng",
    dpi: int = 300,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None
) -> str:
    """
    Extrait le texte d'un PDF scanné via OCR.
    
    Args:
        pdf_path: Chemin vers le fichier PDF
        lang: Langues Tesseract (défaut: français + anglais)
        dpi: Résolution pour la conversion PDF→Image (plus élevé = meilleure qualité mais plus lent)
        first_page: Première page à traiter (1-indexed, None = toutes)
        last_page: Dernière page à traiter (1-indexed, None = toutes)
    
    Returns:
        Texte extrait concaténé de toutes les pages
    
    Raises:
        FileNotFoundError: Si le fichier PDF n'existe pas
        Exception: Si l'extraction OCR échoue
    """
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"Fichier PDF introuvable: {pdf_path}")
    
    # Conversion PDF → Images
    images = convert_from_path(
        pdf_path,
        dpi=dpi,
        first_page=first_page,
        last_page=last_page
    )
    
    # Extraction OCR page par page
    text_parts = []
    for i, image in enumerate(images, start=1):
        page_text = pytesseract.image_to_string(
            image,
            lang=lang,
            config='--psm 6'  # Mode: bloc de texte uniforme
        )
        text_parts.append(f"--- PAGE {i} ---\n{page_text}")
    
    return "\n".join(text_parts)


def extract_text_from_image(
    image_path: Path | str,
    lang: str = "fra+eng"
) -> str:
    """
    Extrait le texte d'une image unique.
    
    Args:
        image_path: Chemin vers l'image
        lang: Langues Tesseract
    
    Returns:
        Texte extrait
    """
    image = Image.open(image_path)
    return pytesseract.image_to_string(image, lang=lang, config='--psm 6')


def check_ocr_available() -> dict:
    """
    Vérifie que Tesseract est correctement installé.
    
    Returns:
        Dict avec 'available' (bool) et 'version' ou 'error'
    """
    try:
        version = pytesseract.get_tesseract_version()
        return {"available": True, "version": str(version)}
    except Exception as e:
        return {"available": False, "error": str(e)}
