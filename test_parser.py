from pathlib import Path
from src.parsers.awb_parser import AWBParser

# Test rapide
data_dir = Path("data/raw")
parser = AWBParser()

print(f"Recherche de fichiers dans : {data_dir.resolve()}")

files = sorted(list(data_dir.glob("*.pdf")))

if not files:
    print("❌ Aucun fichier PDF trouvé dans data/raw/")
else:
    print(f"📂 {len(files)} fichiers trouvés.")

    for f in files:
        if parser.can_process(f):
            print(f"\nTraitement de : {f.name}")
            try:
                releve = parser.parse(f)
                print(f"   ✅ Période: {releve.periode}")
                print(f"   💰 Solde Initial: {releve.solde_initial:,.2f}")
                print(f"   💰 Solde Final:   {releve.solde_final:,.2f}")
                print(f"   📊 Transactions trouvées: {len(releve.transactions)}")
                
                if releve.is_coherent:
                     print("   ✨ COHÉRENCE VALIDÉE (Calculé == Final)")
                else:
                     diff = releve.solde_calcule - releve.solde_final
                     print(f"   ⚠️ INCOHÉRENCE détectée. Écart: {diff:,.2f}")
                     print(f"      (Calculé: {releve.solde_calcule:,.2f} vs Final: {releve.solde_final:,.2f})")
                     
            except Exception as e:
                print(f"   ❌ Erreur lors du parsing: {str(e)}")
        else:
            print(f"   ⏭️ Ignoré (Format non reconnu): {f.name}")
