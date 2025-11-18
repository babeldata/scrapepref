#!/usr/bin/env python3
"""
Téléchargement de PDF avec Playwright pour contourner les protections anti-bot
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
import time

def download_pdf_with_playwright(pdf_url: str, output_path: Path) -> bool:
    """
    Télécharge un PDF en utilisant Playwright pour contourner les protections anti-bot.

    Args:
        pdf_url: URL du PDF
        output_path: Chemin de sortie

    Returns:
        True si le téléchargement a réussi, False sinon
    """
    with sync_playwright() as p:
        # Lancer le navigateur (Firefox plus stable)
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            print(f"Navigation vers: {pdf_url}")

            # Configuration du téléchargement
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Méthode 1: Attendre le téléchargement automatique
            with page.expect_download(timeout=60000) as download_info:
                page.goto(pdf_url, wait_until='networkidle', timeout=60000)

            download = download_info.value

            # Sauvegarder le fichier
            download.save_as(str(output_path))

            print(f"✅ PDF téléchargé: {output_path}")
            print(f"   Taille: {output_path.stat().st_size / 1024:.2f} Ko")

            return True

        except Exception as e:
            print(f"❌ Erreur lors du téléchargement: {e}")

            # Méthode 2: Télécharger via le contenu de la page
            try:
                print("Tentative alternative...")
                response = page.goto(pdf_url, wait_until='networkidle', timeout=60000)

                if response:
                    # Vérifier le content-type
                    headers = response.headers
                    content_type = headers.get('content-type', '').lower()

                    if 'pdf' in content_type or 'octet-stream' in content_type:
                        # Récupérer le contenu
                        content = response.body()

                        # Vérifier que c'est bien un PDF (magic bytes)
                        if content[:4] == b'%PDF':
                            output_path.write_bytes(content)
                            print(f"✅ PDF téléchargé (méthode alternative): {output_path}")
                            print(f"   Taille: {output_path.stat().st_size / 1024:.2f} Ko")
                            return True
                        else:
                            print(f"❌ Le contenu n'est pas un PDF valide")
                            return False
                    else:
                        print(f"❌ Content-Type inattendu: {content_type}")
                        return False
                else:
                    print("❌ Aucune réponse HTTP")
                    return False

            except Exception as e2:
                print(f"❌ Erreur méthode alternative: {e2}")
                return False

        finally:
            browser.close()


if __name__ == '__main__':
    # L'URL du PDF à tester
    pdf_url = "https://www.prefecturedepolice.interieur.gouv.fr/sites/default/files/Documents/arrete_ndeg2025-01535_du_18_novembre_2025_modifiant_provisoirement_le_stationnement_et_la_circulation_rue_de_ponthieu_a_paris_8eme_le_25_novembre_2025_1.pdf"

    # Dossier de sortie
    output_dir = Path('data/test_pdfs')
    output_path = output_dir / 'test_arrete_playwright.pdf'

    print("=" * 80)
    print("Téléchargement de PDF avec Playwright")
    print("=" * 80)
    print(f"URL: {pdf_url}")
    print(f"Destination: {output_path}")
    print()

    success = download_pdf_with_playwright(pdf_url, output_path)

    print()
    print("=" * 80)
    if success:
        print("✅ Téléchargement réussi!")
    else:
        print("❌ Échec du téléchargement")
    print("=" * 80)
