#!/usr/bin/env python3
"""
Scraper pour les arrêtés de la préfecture de police de Paris
Classification automatique des arrêtés de circulation
"""

import os
import re
import csv
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
import requests

# Chargement des variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# URL de base
BASE_URL = "https://www.prefecturedepolice.interieur.gouv.fr"
ARRETES_URL = f"{BASE_URL}/actualites-et-presse/arretes/accueil-arretes"

# Configuration
SCRAPE_DELAY = float(os.getenv('SCRAPE_DELAY_SECONDS', '2'))
MAX_CONCURRENT = int(os.getenv('MAX_CONCURRENT_PAGES', '5'))
MAX_PAGES = int(os.getenv('MAX_PAGES_TO_SCRAPE', '0'))
PAGE_LOAD_TIMEOUT = int(os.getenv('PAGE_LOAD_TIMEOUT', '90000'))
PDF_DOWNLOAD_TIMEOUT = int(os.getenv('PDF_DOWNLOAD_TIMEOUT', '60000'))
DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'

# Configuration S3
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL') or None

def is_circulation_arrete(titre: str, contenu: str = "") -> bool:
    """
    Détermine si un arrêté concerne la circulation.
    Simple : cherche le mot "circulation" dans le titre.
    
    Args:
        titre: Titre de l'arrêté
        contenu: Contenu textuel de l'arrêté (optionnel, non utilisé)
    
    Returns:
        True si c'est un arrêté de circulation, False sinon
    """
    titre_lower = titre.lower()
    return 'circulation' in titre_lower


def get_s3_client():
    """Initialise le client S3."""
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        return None
    
    config = {
        'aws_access_key_id': AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': AWS_SECRET_ACCESS_KEY,
        'region_name': AWS_REGION
    }
    
    if S3_ENDPOINT_URL:
        config['endpoint_url'] = S3_ENDPOINT_URL
    
    return boto3.client('s3', **config)


def upload_pdf_to_s3(s3_client, pdf_path: Path, s3_key: str) -> Optional[str]:
    """
    Upload un PDF vers S3.
    
    Args:
        s3_client: Client S3
        pdf_path: Chemin local du PDF
        s3_key: Clé S3 (chemin dans le bucket)
    
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
    Gère les redirections et extrait le vrai lien PDF si l'URL pointe vers une page HTML.
    
    Args:
        pdf_url: URL du PDF
        output_path: Chemin de sortie
    
    Returns:
        True si le téléchargement a réussi, False sinon
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream,*/*'
        }
        
        # Première tentative : télécharger directement
        response = requests.get(pdf_url, headers=headers, timeout=PDF_DOWNLOAD_TIMEOUT / 1000, 
                               stream=True, allow_redirects=True)
        response.raise_for_status()
        
        # Vérifier le Content-Type
        content_type = response.headers.get('Content-Type', '').lower()
        
        # Si c'est du HTML, essayer d'extraire le vrai lien PDF
        if 'text/html' in content_type or 'html' in content_type:
            logger.info(f"L'URL pointe vers du HTML, extraction du vrai lien PDF...")
            html_content = response.text
            
            # Chercher un lien PDF dans le HTML
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Chercher un lien direct vers un PDF
            pdf_link = soup.find('a', href=re.compile(r'\.pdf', re.I))
            if not pdf_link:
                # Chercher dans les iframes ou objets
                iframe = soup.find('iframe', src=re.compile(r'\.pdf', re.I))
                if iframe:
                    pdf_link = iframe
                    pdf_href = iframe.get('src')
                else:
                    # Chercher un pattern dans le HTML
                    pdf_match = re.search(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', html_content, re.IGNORECASE)
                    if pdf_match:
                        pdf_href = pdf_match.group(1)
                    else:
                        logger.warning(f"Aucun lien PDF trouvé dans la page HTML: {pdf_url}")
                        return False
            else:
                pdf_href = pdf_link.get('href')
            
            # Construire l'URL complète
            if pdf_href:
                if not pdf_href.startswith('http'):
                    pdf_url = urljoin(pdf_url, pdf_href)
                else:
                    pdf_url = pdf_href
                
                logger.info(f"Nouveau lien PDF trouvé: {pdf_url}")
                # Réessayer avec la nouvelle URL
                response = requests.get(pdf_url, headers=headers, timeout=PDF_DOWNLOAD_TIMEOUT / 1000, 
                                       stream=True, allow_redirects=True)
                response.raise_for_status()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Télécharger le fichier
        with open(output_path, 'wb') as f:
            first_chunk = True
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    if first_chunk:
                        # Vérifier les magic bytes PDF (%PDF) dans le premier chunk
                        if chunk[:4] != b'%PDF':
                            logger.warning(f"Le fichier téléchargé n'est pas un PDF valide (magic bytes: {chunk[:4]}, URL: {pdf_url})")
                            output_path.unlink()
                            return False
                        first_chunk = False
                    f.write(chunk)
        
        # Vérification finale : s'assurer que le fichier est bien un PDF
        with open(output_path, 'rb') as f:
            first_bytes = f.read(4)
            if first_bytes != b'%PDF':
                logger.warning(f"Le fichier téléchargé n'est pas un PDF valide (magic bytes: {first_bytes}, URL: {pdf_url})")
                output_path.unlink()
                return False
        
        logger.info(f"PDF téléchargé: {output_path} ({output_path.stat().st_size} bytes)")
        return True
        
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


def extract_arretes_from_page(page, page_num: int) -> List[Dict]:
    """
    Extrait les arrêtés d'une page de résultats.
    
    Args:
        page: Page Playwright
        page_num: Numéro de page
    
    Returns:
        Liste de dictionnaires contenant les informations des arrêtés
    """
    arretes = []
    
    try:
        # Vérifier que la page est toujours valide
        if page.is_closed():
            logger.error(f"Page {page_num}: La page est fermée")
            return arretes
        
        # Attendre que le contenu soit chargé
        try:
            page.wait_for_load_state('networkidle', timeout=PAGE_LOAD_TIMEOUT)
        except Exception as e:
            logger.warning(f"Page {page_num}: Timeout networkidle, continuation: {e}")
        
        time.sleep(1)  # Délai supplémentaire pour le JavaScript
        
        # Récupérer le HTML
        try:
            html = page.content()
        except Exception as e:
            logger.error(f"Page {page_num}: Impossible de récupérer le HTML: {e}")
            return arretes
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Sauvegarder le HTML pour debug
        debug_path = Path('data') / f'debug_page_{page_num}.html'
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Analyser la structure HTML du site
        # Stratégie : être plus sélectif pour éviter de trouver trop d'éléments non pertinents
        
        # Méthode 1 : Chercher des éléments avec des classes spécifiques aux arrêtés
        arretes_elements = []
        seen_hrefs = set()
        
        specific_elements = soup.find_all(['article', 'div', 'li'], 
                                         class_=re.compile(r'node.*decree|arret|item.*arrete', re.I))
        for elem in specific_elements:
            link = elem.find('a', href=True)
            if link:
                href = link.get('href', '')
                if href and href not in seen_hrefs:
                    text = elem.get_text(strip=True)
                    # Vérifier que c'est vraiment un arrêté
                    if len(text) > 20 and ('arrêté' in text.lower() or 'arrete' in text.lower()):
                        # Vérifier qu'il y a un numéro d'arrêté ou une date (signe d'un vrai arrêté)
                        has_number = re.search(r'\d{4}[\s_-]*\d{3,}', text)
                        has_date = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text)
                        if has_number or has_date:
                            arretes_elements.append(elem)
                            seen_hrefs.add(href)
        
        # Méthode 2 : Si on n'a pas assez, chercher les liens vers des arrêtés/PDFs
        if len(arretes_elements) < 10:
            arretes_links = soup.find_all('a', href=re.compile(r'arret', re.I))
            
            for link in arretes_links:
                href = link.get('href', '')
                if not href or href in seen_hrefs:
                    continue
                
                # Vérifier que le lien pointe vers un arrêté (pas juste un menu)
                href_lower = href.lower()
                if '/arretes/' in href_lower or ('.pdf' in href_lower and 'arrete' in href_lower):
                    # Trouver l'élément parent qui contient ce lien (article, div, li, etc.)
                    parent = link.find_parent(['article', 'div', 'li', 'tr'])
                    if parent and parent not in arretes_elements:
                        # Vérifier que l'élément contient du texte significatif (évite les menus)
                        text = parent.get_text(strip=True)
                        if len(text) > 20 and ('arrêté' in text.lower() or 'arrete' in text.lower()):
                            # Vérifier qu'il y a un numéro ou une date
                            has_number = re.search(r'\d{4}[\s_-]*\d{3,}', text)
                            has_date = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text)
                            if has_number or has_date:
                                arretes_elements.append(parent)
                                seen_hrefs.add(href)
        
        # Si on n'a rien trouvé, fallback sur les éléments avec classes spécifiques
        if not arretes_elements:
            arretes_elements = soup.find_all(['article', 'div'], class_=re.compile(r'arret|item|card', re.I))
            # Filtrer pour ne garder que ceux qui ont un lien et du texte significatif
            arretes_elements = [
                elem for elem in arretes_elements 
                if elem.find('a', href=True) and len(elem.get_text(strip=True)) > 20
            ]
        
        logger.info(f"Page {page_num}: {len(arretes_elements)} éléments trouvés")
        
        # Statistiques pour le debug
        skipped_no_link = 0
        skipped_exception = 0
        extracted_count = 0
        
        for element in arretes_elements:
            try:
                # Vérifier rapidement que l'élément contient un lien valide
                link_elem = element.find('a', href=True)
                if not link_elem:
                    skipped_no_link += 1
                    continue
                
                # Ne pas passer la page pour éviter les conflits de navigation
                arrete = extract_arrete_info(element, page=None)
                if arrete:
                    arretes.append(arrete)
                    extracted_count += 1
                else:
                    # Log pour comprendre pourquoi l'extraction a échoué
                    href = link_elem.get('href', '')
                    logger.debug(f"Extraction échouée pour lien: {href[:100]}")
            except Exception as e:
                skipped_exception += 1
                logger.debug(f"Erreur extraction arrêté: {e}")
                continue
        
        if skipped_no_link > 0 or skipped_exception > 0:
            logger.debug(f"Page {page_num}: {skipped_no_link} sans lien, {skipped_exception} erreurs")
        
        logger.info(f"Page {page_num}: {len(arretes)} arrêtés extraits")
        
    except PlaywrightTimeoutError:
        logger.error(f"Timeout chargement page {page_num}")
    except Exception as e:
        logger.error(f"Erreur extraction page {page_num}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    return arretes


def extract_arrete_info(element, page=None) -> Optional[Dict]:
    """
    Extrait les informations d'un arrêté depuis un élément HTML.
    
    Args:
        element: Élément BeautifulSoup
        page: Page Playwright (optionnel, non utilisé pour éviter les conflits)
    
    Returns:
        Dictionnaire avec les informations de l'arrêté ou None
    """
    try:
        # Structure du site : les arrêtés sont dans des <a> avec des <div class="node node--type--tc13-decree">
        # Si l'élément est un <a>, prendre son contenu. Sinon, chercher le <a> parent ou enfant.
        if element.name == 'a':
            link_elem = element
            content_elem = element
        else:
            # Chercher le lien dans l'élément ou ses parents
            link_elem = element.find('a', href=True)
            if not link_elem:
                # Peut-être que l'élément parent est le <a>
                link_elem = element.find_parent('a', href=True)
                if link_elem:
                    content_elem = link_elem
                else:
                    # Pas de lien trouvé, on ne peut pas extraire
                    return None
            else:
                content_elem = element
        
        # Extraire le lien
        lien = link_elem.get('href', '')
        if not lien:
            # Si pas de lien, on peut quand même essayer d'extraire les infos
            # (certains arrêtés peuvent être affichés sans lien cliquable)
            lien = ""
        else:
            if not lien.startswith('http'):
                lien = urljoin(BASE_URL, lien)
        
        # Extraire le titre - chercher dans plusieurs endroits selon la structure du site
        titre = ""
        
        # Méthode 1 : Chercher dans un <span> (structure typique du site)
        titre_elem = content_elem.find('span')
        if titre_elem:
            titre = titre_elem.get_text(strip=True)
        
        # Méthode 2 : Chercher dans les headings
        if not titre:
            titre_elem = content_elem.find(['h1', 'h2', 'h3', 'h4'], class_=re.compile(r'title|titre', re.I))
            if not titre_elem:
                titre_elem = content_elem.find(['h1', 'h2', 'h3', 'h4'])
            if titre_elem:
                titre = titre_elem.get_text(strip=True)
        
        # Méthode 3 : Chercher dans le texte de l'élément avec "Arrêté"
        if not titre or len(titre) < 10:
            texte_complet = content_elem.get_text(separator=' ', strip=True)
            # Chercher le titre qui commence par "Arrêté"
            titre_match = re.search(r'(arrêté[^.]{10,300})', texte_complet, re.IGNORECASE | re.DOTALL)
            if titre_match:
                titre = titre_match.group(1).strip()
        
        # Méthode 4 : Prendre le texte de l'élément si on n'a toujours rien
        if not titre or len(titre) < 10:
            titre = content_elem.get_text(separator=' ', strip=True)
            # Nettoyer : prendre jusqu'à 200 caractères ou jusqu'à un point
            if len(titre) > 200:
                titre = titre[:200].rsplit('.', 1)[0] + '.'
        
        # Si le titre est juste un mois, chercher ailleurs
        mois = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 
                'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
        if titre.lower().strip() in mois:
            # Chercher le vrai titre dans le contenu
            texte_complet = content_elem.get_text(separator=' ', strip=True)
            titre_match = re.search(r'(arrêté[^.]{10,300})', texte_complet, re.IGNORECASE | re.DOTALL)
            if titre_match:
                titre = titre_match.group(1).strip()
        
        if not titre or len(titre) < 5:
            # Dernier recours : utiliser le nom du fichier PDF si disponible
            if '.pdf' in lien.lower():
                titre = lien.split('/')[-1].replace('.pdf', '').replace('_', ' ').replace('-', ' ')
            else:
                titre = "Titre non trouvé"
        
        # Extraire la date - chercher plusieurs formats
        date_publication = ""
        
        # Méthode 1 : Chercher dans les champs de date spécifiques du site
        date_elem = content_elem.find('div', class_=re.compile(r'field.*decree.*date|decree-date', re.I))
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # Extraire la date du texte
            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', date_text)
            if date_match:
                date_publication = date_match.group(1)
        
        # Méthode 2 : Chercher dans les éléments time ou avec classe date
        if not date_publication:
            date_elem = content_elem.find(['time', 'span', 'div'], class_=re.compile(r'date', re.I))
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', date_text)
                if date_match:
                    date_publication = date_match.group(1)
        
        # Méthode 3 : Chercher un pattern de date dans tout le texte
        if not date_publication:
            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', content_elem.get_text())
            if date_match:
                date_publication = date_match.group(1)
        
        # Extraire un aperçu du contenu depuis l'élément actuel
        contenu = ""
        contenu_elem = content_elem.find(['div', 'p', 'span'], class_=re.compile(r'content|texte|summary|description', re.I))
        if contenu_elem:
            contenu = contenu_elem.get_text(strip=True)
        else:
            # Prendre le texte de l'élément entier comme fallback
            contenu = content_elem.get_text(separator=' ', strip=True)
        
        # Extraire le numéro d'arrêté (si présent) - chercher dans le titre ET le contenu
        numero_arrete = ""
        # Pattern pour numéro d'arrêté : 2024-12345 ou 2024_12345 ou 2024 12345
        numero_match = re.search(r'(\d{4}[\s_-]*[A-Z]?[\s_-]*\d{3,})', titre)
        if not numero_match:
            # Chercher aussi dans le contenu avec "arrêté n°"
            numero_match = re.search(r'arrêté\s+n[°o]?\s*(\d{4}[\s_-]*[A-Z]?[\s_-]*\d{3,})', 
                                    f"{titre} {contenu}", re.IGNORECASE)
        if numero_match:
            numero_arrete = numero_match.group(1).strip().replace('_', '-').replace(' ', '-')
        
        # Nettoyer le titre : ne garder que la partie correspondant à ce numéro d'arrêté
        # (seulement si on a plusieurs arrêtés concaténés)
        if numero_arrete and len(titre) > 200:
            # Chercher le titre complet de cet arrêté spécifique
            # Pattern : "Arrêté n°XXXX-XXXXX ..." jusqu'au prochain arrêté ou date
            titre_pattern = rf'arrêté\s+n[°o]?\s*{re.escape(numero_arrete)}[^0-9]*?(?=\d{{1,2}}/\d{{1,2}}/\d{{4}}\s*arrêté|arrêté\s+n[°o]?\s*\d{{4}}|$)'
            titre_match = re.search(titre_pattern, f"{titre} {contenu}", re.IGNORECASE | re.DOTALL)
            if titre_match:
                titre = titre_match.group(0).strip()
                # Nettoyer : enlever les dates en fin de titre qui appartiennent au suivant
                titre = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{4}\s*$', '', titre)
            else:
                # Fallback : prendre jusqu'à la première date suivie d'un autre arrêté
                titre = re.sub(r'(\s+\d{1,2}/\d{1,2}/\d{4}\s+arrêté).*$', '', titre, flags=re.IGNORECASE)
        
        # Nettoyer le contenu : ne garder que la partie correspondant à cet arrêté
        # (seulement si on a plusieurs arrêtés concaténés)
        if numero_arrete and contenu and len(contenu) > 300:
            # Chercher le contenu de cet arrêté spécifique
            contenu_pattern = rf'arrêté\s+n[°o]?\s*{re.escape(numero_arrete)}[^0-9]*?(?=\d{{1,2}}/\d{{1,2}}/\d{{4}}\s*arrêté|arrêté\s+n[°o]?\s*\d{{4}}|$)'
            contenu_match = re.search(contenu_pattern, contenu, re.IGNORECASE | re.DOTALL)
            if contenu_match:
                contenu = contenu_match.group(0).strip()
                # Nettoyer : enlever les dates en fin qui appartiennent au suivant
                contenu = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{4}\s*$', '', contenu)
            else:
                # Fallback : prendre jusqu'à la première date suivie d'un autre arrêté
                contenu = re.sub(r'(\s+\d{1,2}/\d{1,2}/\d{4}\s+arrêté).*$', '', contenu, flags=re.IGNORECASE)
        
        # Chercher le lien PDF - sur ce site, le lien PDF est souvent directement dans le <a>
        pdf_url = None
        
        # Méthode 1 : Le lien lui-même est un PDF (structure typique du site)
        if link_elem and '.pdf' in lien.lower():
            pdf_url = lien
        
        # Méthode 2 : Chercher un lien enfant vers un PDF
        if not pdf_url:
            pdf_link_elem = content_elem.find('a', href=re.compile(r'\.pdf', re.I))
            if pdf_link_elem:
                pdf_href = pdf_link_elem.get('href', '')
                if pdf_href:
                    pdf_url = urljoin(BASE_URL, pdf_href)
        
        # Méthode 3 : Chercher dans les attributs data-* ou autres
        if not pdf_url:
            for attr in ['data-pdf', 'data-url', 'data-href', 'data-file']:
                pdf_attr = content_elem.get(attr, '')
                if pdf_attr and '.pdf' in pdf_attr.lower():
                    pdf_url = urljoin(BASE_URL, pdf_attr)
                    break
        
        # Méthode 4 : Chercher dans le texte HTML de l'élément
        if not pdf_url:
            pdf_match = re.search(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', str(content_elem))
            if pdf_match:
                pdf_url = urljoin(BASE_URL, pdf_match.group(1))
        
        # Si on a trouvé un lien, vérifier qu'il ne pointe pas vers une page HTML
        # (certains sites utilisent des URLs sans .pdf qui redirigent vers le PDF)
        if pdf_url and not pdf_url.lower().endswith('.pdf'):
            # C'est peut-être une URL qui redirige vers le PDF, on la garde
            # La fonction download_pdf gérera l'extraction si c'est du HTML
            pass
        
        # Classifier l'arrêté
        is_circulation = is_circulation_arrete(titre, contenu)
        
        # Générer un hash pour le fichier
        file_hash = hashlib.md5(f"{numero_arrete}{titre}".encode()).hexdigest()[:8]
        
        arrete = {
            'numero_arrete': numero_arrete,
            'titre': titre,
            'date_publication': date_publication,
            'lien': lien,
            'pdf_url': pdf_url or "",
            'is_circulation': is_circulation,
            'contenu_preview': contenu[:200] if contenu else "",  # Premiers 200 caractères
            'file_hash': file_hash,
            'date_scrape': datetime.now().isoformat()
        }
        
        return arrete
    
    except Exception as e:
        logger.error(f"Erreur extraction info arrêté: {e}")
        return None


def scrape_arretes():
    """Fonction principale de scraping."""
    logger.info("Démarrage du scraper des arrêtés de la préfecture de police")
    
    # Vérifier la configuration S3
    global DRY_RUN
    s3_client = None
    if not DRY_RUN:
        s3_client = get_s3_client()
        if not s3_client:
            logger.warning("Configuration S3 incomplète. Mode DRY_RUN activé.")
            DRY_RUN = True
    
    all_arretes = []
    
    playwright_instance = None
    browser = None
    context = None
    page = None
    
    try:
        logger.info("Initialisation de Playwright...")
        playwright_instance = sync_playwright().start()
        logger.info("Playwright démarré")
        
        logger.info("Lancement du navigateur...")
        try:
            # Essayer d'abord avec Firefox (plus stable sur macOS parfois)
            try:
                browser = playwright_instance.firefox.launch(headless=True)
                logger.info("Navigateur Firefox lancé avec succès")
            except Exception as firefox_error:
                logger.warning(f"Firefox non disponible: {firefox_error}, essai avec Chromium...")
                # Fallback sur Chromium avec moins d'arguments pour éviter les crashes
                browser = playwright_instance.chromium.launch(
                    headless=True
                )
                logger.info("Navigateur Chromium lancé avec succès")
        except PlaywrightError as e:
            logger.error(f"Erreur lors du lancement du navigateur: {e}")
            logger.error("Vérifiez que Playwright est correctement installé: playwright install chromium")
            return all_arretes
        except Exception as e:
            logger.error(f"Erreur inattendue lors du lancement: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return all_arretes
        
        try:
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            logger.info("Contexte créé")
            
            page = context.new_page()
            logger.info("Page créée")
        except Exception as e:
            logger.error(f"Erreur lors de la création du contexte/page: {e}")
            if browser:
                browser.close()
            if playwright_instance:
                playwright_instance.stop()
            return all_arretes
        
        # Aller sur la page d'accueil des arrêtés
        logger.info(f"Chargement: {ARRETES_URL}")
        try:
            response = page.goto(ARRETES_URL, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
            if response:
                logger.info(f"Page chargée, status: {response.status}")
            else:
                logger.warning("Aucune réponse HTTP reçue")
            time.sleep(3)  # Délai pour le JavaScript
            logger.info("Page prête")
        except PlaywrightTimeoutError as e:
            logger.warning(f"Timeout lors du chargement de la page: {e}")
            # Essayer quand même de récupérer le contenu
            try:
                html = page.content()
                logger.info(f"HTML récupéré malgré le timeout ({len(html)} caractères)")
            except Exception as e2:
                logger.error(f"Impossible de récupérer le HTML: {e2}")
                return all_arretes
        except Exception as e:
            logger.error(f"Erreur chargement page initiale: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return all_arretes
        
        # Chercher la pagination
        page_num = 1
        while True:
            # Vérifier que la page est toujours valide
            try:
                if page.is_closed():
                    logger.warning(f"Page fermée à la page {page_num}")
                    break
            except Exception:
                logger.warning(f"Impossible de vérifier l'état de la page")
                break
            
            logger.info(f"Traitement page {page_num}")
            
            # Extraire les arrêtés de la page actuelle
            try:
                arretes = extract_arretes_from_page(page, page_num)
                all_arretes.extend(arretes)
            except Exception as e:
                logger.error(f"Erreur extraction page {page_num}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # Continuer avec la page suivante si possible
                try:
                    if page.is_closed():
                        break
                except:
                    break
            
            # Limiter le nombre de pages si configuré
            if MAX_PAGES > 0 and page_num >= MAX_PAGES:
                logger.info(f"Limite de pages atteinte: {MAX_PAGES}")
                break
            
            # Chercher le lien "page suivante"
            try:
                if page.is_closed():
                    break
                
                next_button = page.query_selector('a[aria-label*="suivant"], a:has-text("Suivant"), .pagination a:has-text(">")')
                if not next_button:
                    # Chercher dans le HTML
                    html = page.content()
                    soup = BeautifulSoup(html, 'lxml')
                    next_link = soup.find('a', string=re.compile(r'suivant|next', re.I))
                    if not next_link:
                        logger.info("Aucune page suivante trouvée")
                        break
                    next_url = urljoin(BASE_URL, next_link['href'])
                    page.goto(next_url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
                else:
                    next_button.click()
                    page.wait_for_load_state('domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
                
                page_num += 1
                time.sleep(SCRAPE_DELAY)
                
            except Exception as e:
                logger.info(f"Fin de la pagination: {e}")
                break
    
    except Exception as e:
        logger.error(f"Erreur critique dans le scraping: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    finally:
        # Fermer proprement toutes les ressources
        try:
            if page:
                page.close()
                logger.info("Page fermée")
        except:
            pass
        
        try:
            if context:
                context.close()
                logger.info("Contexte fermé")
        except:
            pass
        
        try:
            if browser:
                browser.close()
                logger.info("Navigateur fermé")
        except:
            pass
        
        try:
            if playwright_instance:
                playwright_instance.stop()
                logger.info("Playwright arrêté")
        except:
            pass
    
    logger.info(f"Total arrêtés extraits: {len(all_arretes)}")
    
    # Télécharger les PDFs et uploader vers S3
    if s3_client:
        data_dir = Path('data')
        data_dir.mkdir(exist_ok=True)
        
        for arrete in all_arretes:
            if arrete.get('pdf_url'):
                try:
                    # Nom du fichier PDF
                    numero_clean = re.sub(r'[^\w\s-]', '', arrete['numero_arrete']).strip()
                    if not numero_clean:
                        numero_clean = "arrete"
                    
                    annee = datetime.now().year
                    pdf_filename = f"{numero_clean}_{arrete['file_hash']}.pdf"
                    pdf_path = data_dir / pdf_filename
                    
                    # Télécharger le PDF (utilise requests au lieu de Playwright)
                    if download_pdf(arrete['pdf_url'], pdf_path):
                        # Upload vers S3
                        s3_key = f"arretes/{annee}/{pdf_filename}"
                        s3_url = upload_pdf_to_s3(s3_client, pdf_path, s3_key)
                        if s3_url:
                            arrete['pdf_s3_url'] = s3_url
                            arrete['poids_pdf_ko'] = round(pdf_path.stat().st_size / 1024, 2)
                        # Supprimer le fichier local
                        pdf_path.unlink()
                    else:
                        arrete['pdf_s3_url'] = "ERROR: PDF non téléchargé"
                    
                    time.sleep(SCRAPE_DELAY)
                
                except Exception as e:
                    logger.error(f"Erreur traitement PDF {arrete.get('pdf_url')}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    arrete['pdf_s3_url'] = "ERROR: PDF non téléchargé"
    
    # Sauvegarder dans CSV
    save_to_csv(all_arretes)
    
    # Statistiques
    total = len(all_arretes)
    circulation = sum(1 for a in all_arretes if a.get('is_circulation'))
    autres = total - circulation
    
    logger.info(f"Statistiques:")
    logger.info(f"  Total arrêtés: {total}")
    logger.info(f"  Arrêtés de circulation: {circulation}")
    logger.info(f"  Autres arrêtés: {autres}")
    
    return all_arretes


def save_to_csv(arretes: List[Dict]):
    """Sauvegarde les arrêtés dans un fichier CSV."""
    if not arretes:
        logger.warning("Aucun arrêté à sauvegarder")
        return
    
    csv_path = Path('data') / 'arretes.csv'
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Colonnes du CSV
    columns = [
        'numero_arrete', 'titre', 'date_publication', 'lien', 'pdf_url',
        'is_circulation', 'contenu_preview', 'pdf_s3_url', 'poids_pdf_ko', 'date_scrape'
    ]
    
    # Créer ou mettre à jour le CSV
    df_new = pd.DataFrame(arretes)
    
    if csv_path.exists():
        df_existing = pd.read_csv(csv_path)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        # Supprimer les doublons basés sur numero_arrete et date_scrape
        df_combined = df_combined.drop_duplicates(subset=['numero_arrete', 'date_publication'], keep='last')
        df_combined.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info(f"CSV mis à jour: {len(df_combined)} arrêtés (dont {len(df_new)} nouveaux)")
    else:
        df_new.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info(f"CSV créé: {len(df_new)} arrêtés")
    
    # Sauvegarder aussi un CSV séparé pour les arrêtés de circulation
    df_circulation = df_new[df_new['is_circulation'] == True]
    if not df_circulation.empty:
        csv_circulation_path = Path('data') / 'arretes_circulation.csv'
        if csv_circulation_path.exists():
            df_existing_circ = pd.read_csv(csv_circulation_path)
            df_combined_circ = pd.concat([df_existing_circ, df_new], ignore_index=True)
            df_combined_circ = df_combined_circ.drop_duplicates(subset=['numero_arrete', 'date_publication'], keep='last')
            df_combined_circ = df_combined_circ[df_combined_circ['is_circulation'] == True]
            df_combined_circ.to_csv(csv_circulation_path, index=False, encoding='utf-8')
        else:
            df_circulation.to_csv(csv_circulation_path, index=False, encoding='utf-8')
        logger.info(f"CSV circulation créé: {len(df_circulation)} arrêtés de circulation")


if __name__ == '__main__':
    scrape_arretes()

