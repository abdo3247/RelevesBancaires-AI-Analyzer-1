import pdfplumber
from pathlib import Path

file_path = Path("Antigravity/data/raw/Relevé_AWB_01-2025_ZPT.pdf")

print(f"Analyse du fichier : {file_path}")
try:
    with pdfplumber.open(file_path) as pdf:
        if len(pdf.pages) > 0:
            page = pdf.pages[0]
            text = page.extract_text()
            print(f"--- Texte extrait (Page 1) ---")
            print(f"'{text}'")
            print(f"------------------------------")
            
            if not text or len(text.strip()) < 10:
                print("⚠️  ALERTE: Très peu de texte détecté. C'est probablement un PDF scanné (Image).")
                print("   Pour traiter ce fichier, il faut un moteur OCR (Tesseract) ou saisir les données manuellement.")
        else:
            print("❌ Aucune page trouvée.")
except Exception as e:
    print(f"❌ Erreur: {e}")
