#!/usr/bin/env python3
"""
Téléchargement de PDF avec requests et headers complets pour simuler un navigateur
"""

import sys
from pathlib import Path
import requests
from urllib.parse import urlparse
import time

def download_pdf_advanced(pdf_url: str, output_path: Path, max_retries: int = 3) -> bool:
    """
    Télécharge un PDF en simulant un vrai navigateur avec des headers complets.

    Args:
        pdf_url: URL du PDF
        output_path: Chemin de sortie
        max_retries: Nombre de tentatives

    Returns:
        True si le téléchargement a réussi, False sinon
    """
    # Headers pour simuler un vrai navigateur
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }

    session = requests.Session()
    session.headers.update(headers)

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Tentative {attempt}/{max_retries}...")

            # Étape 1: Accéder à la page d'accueil pour obtenir les cookies
            print("Étape 1: Accès à la page d'accueil pour initialiser la session...")
            base_url = f"{urlparse(pdf_url).scheme}://{urlparse(pdf_url).netloc}"
            home_response = session.get(base_url, timeout=10)
            home_response.raise_for_status()
            print(f"  Cookies reçus: {len(session.cookies)} cookie(s)")
            time.sleep(1)

            # Étape 2: Télécharger le PDF
            print(f"Étape 2: Téléchargement du PDF depuis {pdf_url}...")

            # Mettre à jour le referer
            session.headers.update({
                'Referer': base_url
            })

            response = session.get(pdf_url, timeout=60, stream=True, allow_redirects=True)

            # Vérifier le code de statut
            if response.status_code == 403:
                print(f"  ⚠️ Erreur 403 Forbidden - tentative avec d'autres headers...")
                # Essayer avec des headers différents
                session.headers.update({
                    'Accept': 'application/pdf,application/octet-stream,*/*',
                    'Sec-Fetch-Dest': 'iframe',
                })
                response = session.get(pdf_url, timeout=60, stream=True, allow_redirects=True)

            response.raise_for_status()

            # Vérifier le content-type
            content_type = response.headers.get('Content-Type', '').lower()
            print(f"  Content-Type: {content_type}")
            print(f"  URL finale: {response.url}")

            # Si c'est du HTML, on ne peut pas continuer
            if 'text/html' in content_type:
                print(f"  ⚠️ Le serveur renvoie du HTML au lieu d'un PDF")
                if attempt < max_retries:
                    print(f"  Nouvelle tentative dans 2 secondes...")
                    time.sleep(2)
                    continue
                return False

            # Créer le dossier de sortie
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Télécharger le fichier
            print(f"  Téléchargement en cours...")
            with open(output_path, 'wb') as f:
                total_size = 0
                first_chunk = True
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        if first_chunk:
                            # Vérifier les magic bytes PDF
                            if chunk[:4] != b'%PDF':
                                print(f"  ⚠️ Le fichier n'est pas un PDF valide (magic bytes: {chunk[:20]})")
                                if attempt < max_retries:
                                    print(f"  Nouvelle tentative dans 2 secondes...")
                                    time.sleep(2)
                                    continue
                                return False
                            first_chunk = False
                        f.write(chunk)
                        total_size += len(chunk)

            # Vérification finale
            with open(output_path, 'rb') as f:
                first_bytes = f.read(4)
                if first_bytes != b'%PDF':
                    print(f"  ⚠️ Le fichier téléchargé n'est pas un PDF valide")
                    output_path.unlink()
                    if attempt < max_retries:
                        print(f"  Nouvelle tentative dans 2 secondes...")
                        time.sleep(2)
                        continue
                    return False

            file_size_kb = total_size / 1024
            file_size_mb = file_size_kb / 1024
            print(f"✅ PDF téléchargé avec succès: {output_path}")
            print(f"   Taille: {file_size_kb:.2f} Ko ({file_size_mb:.2f} Mo)")
            return True

        except requests.exceptions.HTTPError as e:
            print(f"❌ Erreur HTTP: {e}")
            if e.response.status_code == 403:
                print("  Le serveur refuse la connexion (403 Forbidden)")
                print("  Cela peut être dû à une protection anti-bot")
            if attempt < max_retries:
                print(f"  Nouvelle tentative dans 2 secondes...")
                time.sleep(2)
            continue

        except requests.exceptions.Timeout:
            print(f"❌ Timeout lors du téléchargement")
            if attempt < max_retries:
                print(f"  Nouvelle tentative dans 2 secondes...")
                time.sleep(2)
            continue

        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur lors du téléchargement: {e}")
            if attempt < max_retries:
                print(f"  Nouvelle tentative dans 2 secondes...")
                time.sleep(2)
            continue

        except Exception as e:
            print(f"❌ Erreur inattendue: {e}")
            import traceback
            traceback.print_exc()
            return False

    print(f"❌ Échec après {max_retries} tentatives")
    return False


if __name__ == '__main__':
    # L'URL du PDF à tester
    pdf_url = "https://www.prefecturedepolice.interieur.gouv.fr/sites/default/files/Documents/arrete_ndeg2025-01535_du_18_novembre_2025_modifiant_provisoirement_le_stationnement_et_la_circulation_rue_de_ponthieu_a_paris_8eme_le_25_novembre_2025_1.pdf"

    # Dossier de sortie
    output_dir = Path('data/test_pdfs')
    output_path = output_dir / 'test_arrete_requests.pdf'

    print("=" * 80)
    print("Téléchargement de PDF avec requests (headers avancés)")
    print("=" * 80)
    print(f"URL: {pdf_url[:80]}...")
    print(f"Destination: {output_path}")
    print()

    success = download_pdf_advanced(pdf_url, output_path)

    print()
    print("=" * 80)
    if success:
        print("✅ Téléchargement réussi!")
        print(f"   Vous pouvez ouvrir le PDF avec:")
        print(f"   xdg-open {output_path}")
    else:
        print("❌ Échec du téléchargement")
        print()
        print("💡 Note: Ce site utilise probablement une protection anti-bot avancée.")
        print("   Solutions possibles:")
        print("   1. Utiliser un navigateur automatisé (Selenium/Playwright)")
        print("   2. Extraire les PDFs depuis la page web principale")
        print("   3. Utiliser un proxy ou VPN")
    print("=" * 80)
