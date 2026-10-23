from django.core.exceptions import ValidationError

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def validate_upload_image(file):
    if not file:
        return
    size = getattr(file, "size", 0) or 0
    if size > MAX_IMAGE_BYTES:
        raise ValidationError("Image must be 5 MB or smaller.")
    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError("Only JPEG, PNG, WebP, or GIF images are allowed.")
