#!/usr/bin/env python3
"""
Téléchargement de PDF en suivant les redirections JavaScript
"""

import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time

def download_pdf_with_js_redirect(pdf_url: str, output_path: Path, max_redirects: int = 5) -> bool:
    """
    Télécharge un PDF en suivant les redirections JavaScript.

    Args:
        pdf_url: URL du PDF
        output_path: Chemin de sortie
        max_redirects: Nombre maximum de redirections à suivre

    Returns:
        True si le téléchargement a réussi, False sinon
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
    }

    session = requests.Session()
    session.headers.update(headers)

    current_url = pdf_url
    redirect_count = 0

    # Étape 1: Obtenir un cookie de session depuis la page d'accueil
    try:
        from urllib.parse import urlparse
        base_url = f"{urlparse(pdf_url).scheme}://{urlparse(pdf_url).netloc}"
        print(f"Initialisation de la session sur {base_url}...")
        session.get(base_url, timeout=10)
        print(f"  Cookies: {len(session.cookies)} cookie(s) reçu(s)")
        time.sleep(0.5)
    except Exception as e:
        print(f"  Avertissement: impossible d'initialiser la session: {e}")

    # Étape 2: Suivre les redirections JavaScript
    while redirect_count < max_redirects:
        try:
            print(f"\nTentative {redirect_count + 1}: {current_url[:80]}...")

            # Télécharger le contenu
            response = session.get(current_url, timeout=30, stream=False, allow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()
            print(f"  Content-Type: {content_type}")

            # Si c'est un PDF, on a terminé!
            if 'application/pdf' in content_type or 'application/octet-stream' in content_type:
                print("  ✅ PDF trouvé!")

                # Vérifier les magic bytes
                if response.content[:4] != b'%PDF':
                    print(f"  ⚠️ Le contenu n'est pas un PDF valide (magic bytes: {response.content[:20]})")
                    return False

                # Sauvegarder le PDF
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)

                file_size_kb = len(response.content) / 1024
                file_size_mb = file_size_kb / 1024
                print(f"✅ PDF téléchargé avec succès: {output_path}")
                print(f"   Taille: {file_size_kb:.2f} Ko ({file_size_mb:.2f} Mo)")
                return True

            # Si c'est du HTML, chercher une redirection JavaScript
            elif 'text/html' in content_type:
                print("  HTML détecté, recherche de redirection JavaScript...")

                soup = BeautifulSoup(response.text, 'html.parser')

                # Méthode 1: Chercher window.location dans les scripts
                redirect_url = None
                scripts = soup.find_all('script')
                for script in scripts:
                    script_text = script.get_text()

                    # window.location.href = '/redirect_...'
                    match = re.search(r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", script_text)
                    if match:
                        redirect_url = match.group(1)
                        break

                    # window.location = '/redirect_...'
                    match = re.search(r"window\.location\s*=\s*['\"]([^'\"]+)['\"]", script_text)
                    if match:
                        redirect_url = match.group(1)
                        break

                if redirect_url:
                    # Construire l'URL complète
                    if not redirect_url.startswith('http'):
                        redirect_url = urljoin(current_url, redirect_url)

                    print(f"  → Redirection JavaScript trouvée: {redirect_url[:80]}...")
                    current_url = redirect_url
                    redirect_count += 1
                    time.sleep(0.5)  # Petit délai pour ne pas être bloqué
                    continue

                # Méthode 2: Chercher une balise meta refresh
                meta_refresh = soup.find('meta', attrs={'http-equiv': re.compile(r'refresh', re.I)})
                if meta_refresh:
                    content = meta_refresh.get('content', '')
                    match = re.search(r'url=([^\s;]+)', content, re.I)
                    if match:
                        redirect_url = match.group(1)
                        if not redirect_url.startswith('http'):
                            redirect_url = urljoin(current_url, redirect_url)
                        print(f"  → Meta refresh trouvé: {redirect_url[:80]}...")
                        current_url = redirect_url
                        redirect_count += 1
                        time.sleep(0.5)
                        continue

                # Méthode 3: Chercher un lien PDF dans le HTML
                pdf_link = soup.find('a', href=re.compile(r'\.pdf', re.I))
                if pdf_link:
                    redirect_url = pdf_link.get('href')
                    if not redirect_url.startswith('http'):
                        redirect_url = urljoin(current_url, redirect_url)
                    print(f"  → Lien PDF trouvé: {redirect_url[:80]}...")
                    current_url = redirect_url
                    redirect_count += 1
                    time.sleep(0.5)
                    continue

                print("  ❌ Aucune redirection trouvée dans le HTML")
                print(f"  HTML (premiers 500 caractères):\n{response.text[:500]}")
                return False

            else:
                print(f"  ⚠️ Type de contenu inattendu: {content_type}")
                return False

        except requests.exceptions.HTTPError as e:
            print(f"❌ Erreur HTTP: {e}")
            if e.response.status_code == 403:
                print("  Le serveur refuse la connexion (403 Forbidden)")
            return False

        except requests.exceptions.Timeout:
            print(f"❌ Timeout lors du téléchargement")
            return False

        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur lors du téléchargement: {e}")
            return False

        except Exception as e:
            print(f"❌ Erreur inattendue: {e}")
            import traceback
            traceback.print_exc()
            return False

    print(f"❌ Nombre maximum de redirections atteint ({max_redirects})")
    return False


if __name__ == '__main__':
    # L'URL du PDF à tester
    pdf_url = "https://www.prefecturedepolice.interieur.gouv.fr/sites/default/files/Documents/arrete_ndeg2025-01535_du_18_novembre_2025_modifiant_provisoirement_le_stationnement_et_la_circulation_rue_de_ponthieu_a_paris_8eme_le_25_novembre_2025_1.pdf"

    # Dossier de sortie
    output_dir = Path('data/test_pdfs')
    output_path = output_dir / 'test_arrete_final.pdf'

    print("=" * 80)
    print("Téléchargement de PDF avec suivi des redirections JavaScript")
    print("=" * 80)
    print(f"URL: {pdf_url[:77]}...")
    print(f"Destination: {output_path}")
    print()

    success = download_pdf_with_js_redirect(pdf_url, output_path)

    print()
    print("=" * 80)
    if success:
        print("✅ Téléchargement réussi!")
        print(f"\n💡 Pour ouvrir le PDF:")
        print(f"   xdg-open {output_path}")
    else:
        print("❌ Échec du téléchargement")
    print("=" * 80)
