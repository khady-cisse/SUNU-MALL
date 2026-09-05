"""
Stockage privé des documents KYC.

Deux backends possibles, pilotés par le réglage KYC_STORAGE_BACKEND :
- "s3" (défaut, production/dev) : MinIO, bucket DÉDIÉ privé
  `sunu-mall-private`, lire les documents interdit en lecture publique et
  exposé uniquement via des URLs pré-signées à courte durée.
- "fs" (tests) : FileSystemStorage local temporaire, pour exécuter la suite
  sans dépendre d'une infrastructure S3/MinIO.

Le bucket KYC est volontairement distinct du bucket public (`sunu-mall`) qui
héberge les images de catalogue : les pièces KYC ne doivent JAMAIS être
accessibles par une URL publique.
"""
import logging
import os
import re
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings

logger = logging.getLogger(__name__)


def _s3_storage():
    from storages.backends.s3boto3 import S3Boto3Storage

    return S3Boto3Storage(
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
        signature_version="s3v4",
        bucket_name=settings.KYC_STORAGE_BUCKET,
        default_acl=None,
        file_overwrite=False,
        querystring_auth=True,
        querystring_expire=settings.KYC_PRESIGNED_URL_TTL,
    )


def _fs_storage():
    from django.core.files.storage import FileSystemStorage

    return FileSystemStorage(location=settings.KYC_STORAGE_LOCATION)


_kyc_storage = {}
_kyc_storage_signature = None


def _storage_signature():
    """Réglages qui déterminent l'instance de stockage (test-safe)."""
    return (
        settings.KYC_STORAGE_BACKEND,
        settings.KYC_STORAGE_LOCATION,
        settings.KYC_STORAGE_BUCKET,
        settings.KYC_PRESIGNED_URL_TTL,
    )


def get_kyc_storage():
    """
    Instance de stockage KYC, reconstruite si les réglages changent en cours
    de process (cas des tests qui renversent KYC_STORAGE_BACKEND à "fs").
    """
    global _kyc_storage_signature
    signature = _storage_signature()
    if _kyc_storage_signature != signature:
        backend = "fs" if settings.KYC_STORAGE_BACKEND == "fs" else "s3"
        _kyc_storage[backend] = (
            _fs_storage() if backend == "fs" else _s3_storage()
        )
        _kyc_storage_signature = signature
    backend = "fs" if settings.KYC_STORAGE_BACKEND == "fs" else "s3"
    return _kyc_storage[backend]


def ensure_kyc_bucket():
    """Crée le bucket privé s'il n'existe pas encore (idempotent)."""
    storage = get_kyc_storage()
    if settings.KYC_STORAGE_BACKEND == "fs":
        return
    try:
        storage.bucket.create()
    except Exception as exc:  # noqa: BLE001 - MinIO/boto lèvent des erreurs variées
        # BucketAlreadyOwnedByYou / BucketAlreadyExists : ok, il existe déjà.
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            return
        logger.warning("Impossible de créer le bucket KYC %s : %s", settings.KYC_STORAGE_BUCKET, exc)


_SAFE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|pdf)$", re.IGNORECASE)


def safe_extension(filename):
    """Extension sûre pour le nom de fichier (blanc si inconnue)."""
    _, ext = os.path.splitext(filename or "")
    return ext.lower() if _SAFE_EXT_RE.match(ext) else ".jpg"


def save_document(instance, side, upload):
    """
    Enregistre une pièce (`front` ou `back`) dans le dossier privé du dossier.

    Retourne le chemin stocké (clé MinIO ou chemin FS), à conserver dans le
    champ CharField du modèle.
    """
    storage = get_kyc_storage()
    ensure_kyc_bucket()
    name = f"{instance.folder_key()}{side}{safe_extension(upload.name)}"

    previous = instance.document_front if side == "front" else instance.document_back
    if previous:
        try:
            storage.delete(previous)
        except Exception:  # noqa: BLE001 - une pièce absente ne doit pas bloquer l'upload
            logger.warning("Ancienne pièce KYC introuvable à la suppression : %s", previous)

    return storage.save(name, upload)


def signed_url(stored_name):
    """
    URL pré-signée à courte durée pour consulter une pièce.

    Le point d'accès pré-signé pointe sur le endpoint configuré (interne
    Docker). S'il existe un endpoint public (MINIO_PUBLIC_ENDPOINT), on y
    remplace l'hôte en gardant chemin et signature.
    """
    storage = get_kyc_storage()
    try:
        url = storage.url(stored_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossible de générer l'URL signée de %s : %s", stored_name, exc)
        return ""

    public_endpoint = getattr(settings, "MINIO_PUBLIC_ENDPOINT", "") or ""
    if not public_endpoint:
        return url

    try:
        parts = urlsplit(url)
        public = urlsplit(public_endpoint if "//" in public_endpoint else f"//{public_endpoint}")
        return urlunsplit((public.scheme or parts.scheme, public.netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return url