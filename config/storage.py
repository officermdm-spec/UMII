"""Product photos keep a stable filename and can be found in main or gallery."""

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage

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
