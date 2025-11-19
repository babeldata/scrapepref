#!/usr/bin/env python3
"""
Script de diagnostic pour lister les fichiers sur S3 et voir leur structure.
"""

import os
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL') or None

def get_s3_client():
    """Initialise le client S3."""
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        print("Configuration S3 incomplète.")
        return None
    
    config = {
        'aws_access_key_id': AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': AWS_SECRET_ACCESS_KEY,
        'region_name': AWS_REGION
    }
    
    if S3_ENDPOINT_URL:
        config['endpoint_url'] = S3_ENDPOINT_URL
    
    return boto3.client('s3', **config)


def list_s3_files(s3_client, prefix='arretes/', max_files=20):
    """Liste les fichiers S3 avec le préfixe donné."""
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix)
        
        count = 0
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    size = obj['Size']
                    print(f"{key} ({size} bytes)")
                    count += 1
                    if count >= max_files:
                        return
    except ClientError as e:
        print(f"Erreur: {e}")


if __name__ == '__main__':
    s3_client = get_s3_client()
    if s3_client:
        print(f"Liste des fichiers dans s3://{S3_BUCKET_NAME}/arretes/ (20 premiers):")
        print("-" * 80)
        list_s3_files(s3_client)
    else:
        print("Impossible d'initialiser le client S3")

