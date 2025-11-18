#!/usr/bin/env python3
"""
Script de test local du scraper
"""

import os
import sys
from pathlib import Path

# Ajouter le dossier src au path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Configuration pour le mode test
os.environ.setdefault('DRY_RUN', 'true')
os.environ.setdefault('MAX_PAGES_TO_SCRAPE', '2')  # Limiter à 2 pages pour les tests

print("=" * 60)
print("Mode TEST - Scraper des arrêtés préfecture de police")
print("=" * 60)
print(f"DRY_RUN: {os.getenv('DRY_RUN')}")
print(f"MAX_PAGES_TO_SCRAPE: {os.getenv('MAX_PAGES_TO_SCRAPE')}")
print("=" * 60)
print()

# Vérifier la configuration
if not os.getenv('DRY_RUN') == 'true':
    print("⚠️  ATTENTION: DRY_RUN n'est pas activé!")
    print("   Le scraper va essayer d'uploader vers S3.")
    print("   Pour activer le mode test, définissez DRY_RUN=true")
    print()
    response = input("Continuer quand même? (o/N): ")
    if response.lower() != 'o':
        sys.exit(0)

# Importer et exécuter le scraper
from scraper import scrape_arretes

try:
    arretes = scrape_arretes()
    print()
    print("=" * 60)
    print("✅ Scraping terminé avec succès!")
    print(f"   {len(arretes)} arrêtés extraits")
    print("=" * 60)
except Exception as e:
    print()
    print("=" * 60)
    print("❌ Erreur lors du scraping:")
    print(f"   {e}")
    print("=" * 60)
    sys.exit(1)

