#!/usr/bin/env python3
"""
Script de test pour analyser la structure HTML du site
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

BASE_URL = "https://www.prefecturedepolice.interieur.gouv.fr"
ARRETES_URL = f"{BASE_URL}/actualites-et-presse/arretes/accueil-arretes"

print("=" * 60)
print("Test de structure HTML - Préfecture de police")
print("=" * 60)
print(f"URL: {ARRETES_URL}")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # Mode visible pour debug
    page = browser.new_page()
    
    try:
        print("Chargement de la page...")
        page.goto(ARRETES_URL, wait_until='networkidle', timeout=90000)
        
        # Attendre un peu pour le JavaScript
        page.wait_for_timeout(3000)
        
        # Récupérer le HTML
        html = page.content()
        
        # Sauvegarder pour analyse
        debug_path = Path('debug_local.html')
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"HTML sauvegardé dans: {debug_path}")
        print()
        
        # Analyser avec BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        print("=" * 60)
        print("ANALYSE DE LA STRUCTURE")
        print("=" * 60)
        print()
        
        # Chercher les titres
        print("📋 Titres (h1-h4):")
        for i in range(1, 5):
            headings = soup.find_all(f'h{i}')
            if headings:
                print(f"  h{i}: {len(headings)} trouvés")
                for h in headings[:3]:
                    print(f"    - {h.get_text(strip=True)[:80]}")
        print()
        
        # Chercher les liens
        print("🔗 Liens vers des arrêtés:")
        links = soup.find_all('a', href=re.compile(r'arret', re.I))
        print(f"  {len(links)} liens trouvés")
        for link in links[:5]:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            print(f"    - {text[:60]}")
            print(f"      URL: {href[:80]}")
        print()
        
        # Chercher les articles ou divs avec classes pertinentes
        print("📄 Éléments avec classes 'arrete', 'item', 'card':")
        for class_name in ['arrete', 'item', 'card', 'article', 'news']:
            elements = soup.find_all(['div', 'article'], class_=re.compile(class_name, re.I))
            if elements:
                print(f"  {class_name}: {len(elements)} trouvés")
                for elem in elements[:2]:
                    print(f"    - {elem.get_text(strip=True)[:80]}")
        print()
        
        # Chercher les dates
        print("📅 Éléments avec dates:")
        date_elements = soup.find_all(['time', 'span', 'div'], class_=re.compile(r'date', re.I))
        print(f"  {len(date_elements)} éléments avec 'date' dans la classe")
        for elem in date_elements[:3]:
            print(f"    - {elem.get_text(strip=True)[:60]}")
        print()
        
        # Chercher les PDFs
        print("📎 Liens PDF:")
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
        print(f"  {len(pdf_links)} liens PDF trouvés")
        for link in pdf_links[:3]:
            print(f"    - {link.get('href', '')[:80]}")
        print()
        
        print("=" * 60)
        print("✅ Analyse terminée")
        print("=" * 60)
        print()
        print("💡 Conseils:")
        print("  1. Ouvrez debug_local.html dans un navigateur")
        print("  2. Inspectez les éléments pour identifier les sélecteurs CSS")
        print("  3. Adaptez extract_arretes_from_page() dans scraper.py")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        input("\nAppuyez sur Entrée pour fermer le navigateur...")
        browser.close()

