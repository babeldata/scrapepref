#!/usr/bin/env python3
"""
Script pour rescraper les PDFs manquants dans le CSV et les uploader sur S3.
Identifie les lignes sans pdf_s3_url, télécharge les PDFs et les upload sur S3.
"""

import os
import re
import logging
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Chargement des variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rescrape_missing_s3.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration S3
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL') or None
DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'
SCRAPE_DELAY = float(os.getenv('SCRAPE_DELAY_SECONDS', '2'))
PDF_DOWNLOAD_TIMEOUT = int(os.getenv('PDF_DOWNLOAD_TIMEOUT', '60000'))


def get_s3_client():
    """Initialise le client S3."""
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        logger.error("Configuration S3 incomplète. Vérifiez vos variables d'environnement.")
        return None
    
    config = {
        'aws_access_key_id': AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': AWS_SECRET_ACCESS_KEY,
        'region_name': AWS_REGION
    }
    
    if S3_ENDPOINT_URL:
        config['endpoint_url'] = S3_ENDPOINT_URL
    
    return boto3.client('s3', **config)


def check_s3_file_exists(s3_client, s3_key: str):
    """
    Vérifie si un fichier existe déjà sur S3 et retourne ses métadonnées.
    
    Returns:
        Dictionnaire avec 'size' (taille en bytes) si le fichier existe, None sinon
    """
    if DRY_RUN:
        logger.debug(f"[DRY_RUN] Vérification simulée: {s3_key}")
        return None
    
    try:
        response = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        size = response.get('ContentLength', 0)
        return {'size': size}
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == '404':
            return None
        else:
            logger.warning(f"Erreur vérification S3 {s3_key}: {e}")
            return None


def upload_pdf_to_s3(s3_client, pdf_path: Path, s3_key: str):
    """
    Upload un PDF vers S3.
    
    Returns:
        URL S3 du fichier ou None en cas d'erreur
    """
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Upload simulé: {s3_key}")
        return f"s3://{S3_BUCKET_NAME}/{s3_key}"
    
    try:
        s3_client.upload_file(str(pdf_path), S3_BUCKET_NAME, s3_key)
        s3_url = f"s3://{S3_BUCKET_NAME}/{s3_key}"
        logger.info(f"PDF uploadé: {s3_url}")
        return s3_url
    except ClientError as e:
        logger.error(f"Erreur upload S3: {e}")
        return None


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """
    Télécharge un PDF depuis une URL en utilisant requests.
    Gère les redirections JavaScript utilisées par le site pour la protection anti-bot.
    """
    max_redirects = 5

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
        # Étape 1: Obtenir un cookie de session depuis la page d'accueil
        parsed_url = urlparse(pdf_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        try:
            session.get(base_url, timeout=10)
        except Exception as e:
            logger.debug(f"Impossible d'initialiser la session: {e}")

        # Étape 2: Suivre les redirections JavaScript
        current_url = pdf_url
        redirect_count = 0

        while redirect_count < max_redirects:
            response = session.get(current_url, timeout=PDF_DOWNLOAD_TIMEOUT / 1000,
                                  stream=False, allow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()

            # Si c'est un PDF, on a terminé!
            if 'application/pdf' in content_type or 'application/octet-stream' in content_type:
                # Vérifier les magic bytes
                if response.content[:4] != b'%PDF':
                    logger.warning(f"Le contenu n'est pas un PDF valide (magic bytes: {response.content[:4]}, URL: {current_url})")
                    return False

                # Sauvegarder le PDF
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)

                logger.info(f"PDF téléchargé: {output_path} ({output_path.stat().st_size} bytes)")
                return True

            # Si c'est du HTML, chercher une redirection JavaScript
            elif 'text/html' in content_type:
                soup = BeautifulSoup(response.text, 'lxml')

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

                    logger.debug(f"Redirection JavaScript trouvée: {redirect_url}")
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
                        logger.debug(f"Meta refresh trouvé: {redirect_url}")
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
                    logger.debug(f"Lien PDF trouvé: {redirect_url}")
                    current_url = redirect_url
                    redirect_count += 1
                    time.sleep(0.5)
                    continue

                logger.warning(f"Aucune redirection trouvée dans le HTML: {pdf_url}")
                return False
            else:
                logger.warning(f"Type de contenu inattendu: {content_type}")
                return False

        logger.warning(f"Nombre maximum de redirections atteint ({max_redirects}): {pdf_url}")
        return False

    except requests.exceptions.Timeout:
        logger.error(f"Timeout téléchargement PDF: {pdf_url}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur téléchargement PDF: {e}")
        return False
    except Exception as e:
        logger.error(f"Erreur téléchargement PDF: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def get_project_root() -> Path:
    """Trouve la racine du projet."""
    current = Path(__file__).resolve().parent
    markers = ['.git', 'README.md', 'requirements.txt', 'pyproject.toml']
    
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent
    
    return Path.cwd()


def process_csv(csv_path: Path, s3_client):
    """
    Traite le CSV pour télécharger et uploader les PDFs manquants.
    """
    if not csv_path.exists():
        logger.error(f"Fichier CSV non trouvé: {csv_path}")
        return
    
    logger.info(f"Lecture du CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Vérifier que les colonnes nécessaires existent
    required_columns = ['numero_arrete', 'file_hash', 'pdf_url', 'date_publication']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.error(f"Colonnes manquantes dans le CSV: {missing_columns}")
        return
    
    # Initialiser les colonnes si elles n'existent pas
    if 'pdf_s3_url' not in df.columns:
        df['pdf_s3_url'] = ''
    if 'poids_pdf_ko' not in df.columns:
        df['poids_pdf_ko'] = ''
    
    project_root = get_project_root()
    data_dir = project_root / 'data'
    data_dir.mkdir(exist_ok=True)
    
    # Filtrer les lignes sans pdf_s3_url
    mask = df['pdf_s3_url'].isna() | (df['pdf_s3_url'].astype(str).str.strip() == '') | (df['pdf_s3_url'].astype(str) == 'nan')
    rows_to_process = df[mask].copy()
    
    total_to_process = len(rows_to_process)
    logger.info(f"Nombre de lignes à traiter: {total_to_process}")
    
    if total_to_process == 0:
        logger.info("Aucune ligne à traiter. Tous les fichiers ont déjà un lien S3.")
        return
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    for idx, row in rows_to_process.iterrows():
        numero_arrete = str(row.get('numero_arrete', '')).strip()
        file_hash = str(row.get('file_hash', '')).strip()
        pdf_url = str(row.get('pdf_url', '')).strip()
        date_publication = str(row.get('date_publication', '')).strip()
        
        if not numero_arrete or not file_hash or not pdf_url:
            logger.warning(f"Ligne {idx}: Données manquantes (numero: {numero_arrete}, hash: {file_hash}, url: {bool(pdf_url)})")
            skipped_count += 1
            continue
        
        logger.info(f"Traitement [{success_count + error_count + skipped_count + 1}/{total_to_process}]: {numero_arrete}")
        
        try:
            # Nettoyer le numéro d'arrêté pour le nom de fichier
            numero_clean = re.sub(r'[^\w\s-]', '', numero_arrete).strip()
            if not numero_clean:
                numero_clean = "arrete"
            
            pdf_filename = f"{numero_clean}_{file_hash}.pdf"
            
            # Essayer d'extraire l'année depuis la date de publication
            annee = datetime.now().year
            if date_publication:
                date_match = re.search(r'(\d{4})', date_publication)
                if date_match:
                    annee = int(date_match.group(1))
            
            s3_key = f"arretes/{annee}/{pdf_filename}"
            
            # Vérifier si le fichier existe déjà sur S3
            s3_file_info = check_s3_file_exists(s3_client, s3_key)
            
            if s3_file_info:
                # Le fichier existe déjà, générer l'URL S3
                s3_url = f"s3://{S3_BUCKET_NAME}/{s3_key}"
                poids_ko = round(s3_file_info['size'] / 1024, 2)
                
                df.at[idx, 'pdf_s3_url'] = s3_url
                df.at[idx, 'poids_pdf_ko'] = poids_ko
                
                logger.info(f"✓ Fichier déjà présent sur S3: {s3_url} ({poids_ko} Ko)")
                success_count += 1
            else:
                # Télécharger le PDF
                pdf_path = data_dir / pdf_filename
                
                logger.info(f"Téléchargement: {pdf_url}")
                if download_pdf(pdf_url, pdf_path):
                    # Upload vers S3
                    s3_url = upload_pdf_to_s3(s3_client, pdf_path, s3_key)
                    if s3_url:
                        poids_ko = round(pdf_path.stat().st_size / 1024, 2)
                        
                        df.at[idx, 'pdf_s3_url'] = s3_url
                        df.at[idx, 'poids_pdf_ko'] = poids_ko
                        
                        logger.info(f"✓ Upload réussi: {s3_url} ({poids_ko} Ko)")
                        success_count += 1
                    else:
                        logger.error(f"✗ Échec upload S3 pour {numero_arrete}")
                        df.at[idx, 'pdf_s3_url'] = "ERROR: Upload S3 échoué"
                        error_count += 1
                    
                    # Supprimer le fichier local
                    pdf_path.unlink()
                else:
                    logger.error(f"✗ Échec téléchargement PDF pour {numero_arrete}")
                    df.at[idx, 'pdf_s3_url'] = "ERROR: PDF non téléchargé"
                    error_count += 1
            
            # Délai entre les requêtes
            time.sleep(SCRAPE_DELAY)
        
        except Exception as e:
            logger.error(f"Erreur traitement {numero_arrete}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            df.at[idx, 'pdf_s3_url'] = f"ERROR: {str(e)[:50]}"
            error_count += 1
    
    # Sauvegarder le CSV mis à jour
    df.to_csv(csv_path, index=False, encoding='utf-8')
    logger.info(f"\n{'='*60}")
    logger.info(f"Résumé pour {csv_path.name}:")
    logger.info(f"  - Total à traiter: {total_to_process}")
    logger.info(f"  - Succès: {success_count}")
    logger.info(f"  - Erreurs: {error_count}")
    logger.info(f"  - Ignorés: {skipped_count}")
    logger.info(f"  - CSV mis à jour: {csv_path}")
    logger.info(f"{'='*60}")


def main():
    """Fonction principale."""
    logger.info("Démarrage du rescraping des PDFs manquants")
    
    s3_client = get_s3_client()
    if not s3_client:
        logger.error("Impossible d'initialiser le client S3. Arrêt.")
        return
    
    project_root = get_project_root()
    csv_path = project_root / 'data' / 'arretes_circulation.csv'
    
    if not csv_path.exists():
        logger.error(f"Fichier CSV non trouvé: {csv_path}")
        return
    
    process_csv(csv_path, s3_client)
    
    logger.info("Rescraping terminé")


if __name__ == '__main__':
    main()
