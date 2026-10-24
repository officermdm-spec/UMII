"""Product photos keep a stable filename and can be found in main or gallery."""

import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from django.utils.encoding import filepath_to_uri

PRODUCT_FOLDERS = ("products/main", "products/gallery")


def resolve_public_media(relative_path):
    """Return a media-relative path that exists, matching main/gallery by filename."""
    if not relative_path:
        return None
    relative_path = str(relative_path).replace("\\", "/").lstrip("/")
    root = Path(settings.MEDIA_ROOT)
    direct = root / relative_path
    if direct.is_file():
        return relative_path
    name = Path(relative_path).name
    if not name:
        return None
    for folder in PRODUCT_FOLDERS:
        candidate = root / folder / name
        if candidate.is_file():
            return f"{folder}/{name}"
    return None


class CatalogStorage(FileSystemStorage):
    """Overwrite the same filename so database paths stay stable across uploads."""

    def get_available_name(self, name, max_length=None):
        if super().exists(name):
            self.delete(name)
        return name


def product_image_storage():
    cloudinary_configured = bool(
        os.environ.get("CLOUDINARY_URL")
        or all(
            settings.CLOUDINARY_STORAGE.get(key)
            for key in ("CLOUD_NAME", "API_KEY", "API_SECRET")
        )
    )
    if not cloudinary_configured:
        if os.environ.get("RENDER"):
            raise ImproperlyConfigured(
                "Set CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET on Render."
            )
        return CatalogStorage()

    from cloudinary_storage.storage import MediaCloudinaryStorage

    class ProductCloudinaryStorage(MediaCloudinaryStorage):
        def url(self, name):
            resolved = resolve_public_media(name)
            if resolved:
                return f"{settings.MEDIA_URL.rstrip('/')}/{filepath_to_uri(resolved)}"
            return super().url(name)

    return ProductCloudinaryStorage()
