#!/usr/bin/env python3
"""
Analyser le HTML renvoyé par le serveur
"""

import requests
from bs4 import BeautifulSoup

pdf_url = "https://www.prefecturedepolice.interieur.gouv.fr/sites/default/files/Documents/arrete_ndeg2025-01535_du_18_novembre_2025_modifiant_provisoirement_le_stationnement_et_la_circulation_rue_de_ponthieu_a_paris_8eme_le_25_novembre_2025_1.pdf"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

print("Récupération du HTML...")
response = requests.get(pdf_url, headers=headers)

print(f"Status: {response.status_code}")
print(f"Content-Type: {response.headers.get('Content-Type')}")
print()

# Sauvegarder le HTML
html_path = 'data/test_pdfs/response.html'
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(response.text)

print(f"HTML sauvegardé dans: {html_path}")
print()

# Analyser le HTML
soup = BeautifulSoup(response.text, 'html.parser')

print("=" * 80)
print("ANALYSE DU HTML")
print("=" * 80)
print()

# Afficher le début du HTML
print("Premier 1000 caractères:")
print(response.text[:1000])
print()

# Chercher des scripts
scripts = soup.find_all('script')
print(f"Nombre de scripts: {len(scripts)}")
if scripts:
    print("Premier script:")
    print(scripts[0].get_text()[:500])
print()

# Chercher des meta tags
metas = soup.find_all('meta')
print(f"Meta tags: {len(metas)}")
for meta in metas[:5]:
    print(f"  {meta}")
print()

# Chercher des liens
links = soup.find_all('a')
print(f"Liens: {len(links)}")
for link in links[:5]:
    print(f"  {link.get('href', 'no href')}: {link.get_text(strip=True)[:50]}")
