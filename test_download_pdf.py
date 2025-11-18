#!/usr/bin/env python3
"""
Script de test pour télécharger un PDF spécifique
"""

import sys
from pathlib import Path

# Ajouter le dossier src au path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from scraper import download_pdf

# L'URL du PDF à tester
pdf_url = "https://www.prefecturedepolice.interieur.gouv.fr/sites/default/files/Documents/arrete_ndeg2025-01535_du_18_novembre_2025_modifiant_provisoirement_le_stationnement_et_la_circulation_rue_de_ponthieu_a_paris_8eme_le_25_novembre_2025_1.pdf"

# Dossier de sortie
output_dir = Path('data/test_pdfs')
output_dir.mkdir(parents=True, exist_ok=True)

# Nom du fichier de sortie
output_path = output_dir / 'test_arrete.pdf'

print("=" * 80)
print("Test de téléchargement de PDF")
print("=" * 80)
print(f"URL: {pdf_url}")
print(f"Destination: {output_path}")
print()

# Télécharger le PDF
print("Téléchargement en cours...")
success = download_pdf(pdf_url, output_path)

print()
print("=" * 80)
if success:
    file_size = output_path.stat().st_size
    file_size_kb = file_size / 1024
    file_size_mb = file_size_kb / 1024

    print("✅ Téléchargement réussi!")
    print(f"   Fichier: {output_path}")
    print(f"   Taille: {file_size_kb:.2f} Ko ({file_size_mb:.2f} Mo)")
    print()
    print(f"💡 Vous pouvez ouvrir le PDF avec:")
    print(f"   open {output_path}  # macOS")
    print(f"   xdg-open {output_path}  # Linux")
else:
    print("❌ Échec du téléchargement")
    print("   Vérifiez les logs ci-dessus pour plus de détails")
print("=" * 80)
