from django.conf import settings
from django.http import Http404
from django.views.static import serve

from apps.accounts.permissions import MODULES, has_module_permission
from apps.payments.models import Payment
from apps.returns.models import ReturnImage
from config.storage import resolve_public_media


def protected_media(request, path):
    """Serve public product images, but keep payment/return files private."""
    if path.startswith("payments/"):
        if not request.user.is_authenticated:
            raise Http404()
        payment = (
            Payment.objects.filter(proof_image=path)
            .select_related("order")
            .first()
        )
        if payment is None:
            raise Http404()
        allowed = payment.order.customer_id == request.user.id or has_module_permission(
            request.user, MODULES.PAYMENTS
        )
        if not allowed:
            raise Http404()
    elif path.startswith("returns/"):
        if not request.user.is_authenticated:
            raise Http404()
        image = (
            ReturnImage.objects.filter(image=path)
            .select_related("return_request")
            .first()
        )
        if image is None:
            raise Http404()
        allowed = image.return_request.customer_id == request.user.id or has_module_permission(
            request.user, MODULES.RETURNS
        )
        if not allowed:
            raise Http404()
    else:
        resolved = resolve_public_media(path)
        if not resolved:
            raise Http404()
        path = resolved
    return serve(request, path, document_root=str(settings.MEDIA_ROOT))
