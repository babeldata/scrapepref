#!/usr/bin/env python3
"""
Script pour mettre à jour les URLs S3 dans les CSV existants.
Vérifie si les fichiers existent déjà sur S3 et remplit les colonnes pdf_s3_url et poids_pdf_ko.
"""

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
import pandas as pd

# Chargement des variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update_s3_urls.log'),
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


def find_file_by_hash(s3_client, file_hash: str, prefix='arretes/'):
    """
    Recherche un fichier sur S3 par son hash dans le nom de fichier.
    
    Returns:
        Tuple (s3_key, size) si trouvé, (None, None) sinon
    """
    if DRY_RUN:
        return None, None
    
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    # Chercher le hash dans le nom de fichier
                    if file_hash.lower() in key.lower():
                        size = obj['Size']
                        return key, size
    except ClientError as e:
        logger.warning(f"Erreur recherche par hash: {e}")
    
    return None, None


def get_project_root() -> Path:
    """Trouve la racine du projet."""
    current = Path(__file__).resolve().parent
    markers = ['.git', 'README.md', 'requirements.txt', 'pyproject.toml']
    
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent
    
    return Path.cwd()


def update_csv_s3_urls(csv_path: Path, s3_client):
    """
    Met à jour les URLs S3 dans un fichier CSV.
    """
    if not csv_path.exists():
        logger.warning(f"Fichier CSV non trouvé: {csv_path}")
        return
    
    logger.info(f"Lecture du CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Vérifier que les colonnes nécessaires existent
    required_columns = ['numero_arrete', 'file_hash', 'date_publication']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.error(f"Colonnes manquantes dans le CSV: {missing_columns}")
        return
    
    # Initialiser les colonnes si elles n'existent pas
    if 'pdf_s3_url' not in df.columns:
        df['pdf_s3_url'] = ''
    if 'poids_pdf_ko' not in df.columns:
        df['poids_pdf_ko'] = ''
    
    updated_count = 0
    found_count = 0
    not_found_count = 0
    
    for idx, row in df.iterrows():
        # Vérifier si pdf_s3_url est vide (gérer NaN, None, chaîne vide)
        pdf_s3_url_value = row.get('pdf_s3_url')
        if pd.notna(pdf_s3_url_value) and str(pdf_s3_url_value).strip() and str(pdf_s3_url_value) != '' and str(pdf_s3_url_value) != 'nan':
            continue
        
        numero_arrete = str(row.get('numero_arrete', '')).strip()
        file_hash = str(row.get('file_hash', '')).strip()
        date_publication = str(row.get('date_publication', '')).strip()
        
        if not numero_arrete or not file_hash:
            continue
        
        # Nettoyer le numéro d'arrêté pour le nom de fichier
        numero_clean = re.sub(r'[^\w\s-]', '', numero_arrete).strip()
        if not numero_clean:
            numero_clean = "arrete"
        
        # Essayer d'extraire l'année depuis la date de publication
        annee_publication = datetime.now().year
        if date_publication:
            date_match = re.search(r'(\d{4})', date_publication)
            if date_match:
                annee_publication = int(date_match.group(1))
        
        # Chercher le fichier dans plusieurs années possibles
        annees_a_verifier = [annee_publication]
        annee_actuelle = datetime.now().year
        if annee_actuelle not in annees_a_verifier:
            annees_a_verifier.append(annee_actuelle)
        if annee_actuelle - 1 not in annees_a_verifier:
            annees_a_verifier.append(annee_actuelle - 1)
        
        # Essayer plusieurs formats de noms de fichiers
        formats_a_essayer = [
            f"{numero_clean}_{file_hash}.pdf",  # Format standard: numero_hash.pdf
            f"{file_hash}.pdf",  # Juste le hash
            f"{numero_clean}.pdf",  # Juste le numéro
        ]
        
        # Vérifier si le fichier existe déjà sur S3
        s3_file_info = None
        annee_trouvee = None
        s3_key_trouve = None
        
        # Méthode 1: Chercher avec les formats attendus
        for pdf_filename in formats_a_essayer:
            for annee in annees_a_verifier:
                s3_key = f"arretes/{annee}/{pdf_filename}"
                s3_file_info = check_s3_file_exists(s3_client, s3_key)
                if s3_file_info:
                    annee_trouvee = annee
                    s3_key_trouve = s3_key
                    break
            if s3_file_info:
                break
        
        # Méthode 2: Si pas trouvé, chercher par hash dans tous les fichiers
        if not s3_file_info:
            s3_key_found, size = find_file_by_hash(s3_client, file_hash)
            if s3_key_found:
                s3_file_info = {'size': size}
                s3_key_trouve = s3_key_found
                logger.info(f"Fichier trouvé par hash: {s3_key_found}")
        
        if s3_file_info:
            # Le fichier existe, générer l'URL S3
            s3_url = f"s3://{S3_BUCKET_NAME}/{s3_key_trouve}"
            poids_ko = round(s3_file_info['size'] / 1024, 2)
            
            df.at[idx, 'pdf_s3_url'] = s3_url
            df.at[idx, 'poids_pdf_ko'] = poids_ko
            
            found_count += 1
            updated_count += 1
            logger.info(f"✓ Trouvé: {numero_arrete} -> {s3_url} ({poids_ko} Ko)")
        else:
            not_found_count += 1
            logger.debug(f"✗ Non trouvé: {numero_arrete} (hash: {file_hash})")
    
    # Sauvegarder le CSV mis à jour
    if updated_count > 0:
        df.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info(f"CSV mis à jour: {csv_path}")
        logger.info(f"  - Fichiers trouvés sur S3: {found_count}")
        logger.info(f"  - Fichiers non trouvés: {not_found_count}")
        logger.info(f"  - Total mis à jour: {updated_count}")
    else:
        logger.info(f"Aucune mise à jour nécessaire pour {csv_path}")


def main():
    """Fonction principale."""
    logger.info("Démarrage de la mise à jour des URLs S3 dans les CSV")
    
    s3_client = get_s3_client()
    if not s3_client:
        logger.error("Impossible d'initialiser le client S3. Arrêt.")
        return
    
    project_root = get_project_root()
    data_dir = project_root / 'data'
    
    # Mettre à jour les deux CSV
    csv_files = [
        data_dir / 'arretes.csv',
        data_dir / 'arretes_circulation.csv'
    ]
    
    for csv_path in csv_files:
        if csv_path.exists():
            update_csv_s3_urls(csv_path, s3_client)
        else:
            logger.warning(f"Fichier CSV non trouvé: {csv_path}")
    
    logger.info("Mise à jour terminée")


if __name__ == '__main__':
    main()

