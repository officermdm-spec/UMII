from django.db.models import F, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.mixins import ModulePermissionMixin
from apps.accounts.models import User
from apps.accounts.permissions import MODULES
from apps.orders.models import Order
from apps.products.models import Product
from apps.purchases.models import GRN
from apps.returns.models import ReturnRequest
from apps.vendors.models import Vendor


class DashboardView(ModulePermissionMixin, TemplateView):
    module = MODULES.DASHBOARD
    template_name = "staff/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "total_customers": User.objects.filter(user_type=User.UserType.CUSTOMER).count(),
                "total_products": Product.objects.count(),
                "total_vendors": Vendor.objects.count(),
                "total_orders": Order.objects.count(),
                "pending_orders": Order.objects.filter(status=Order.Status.PENDING).count(),
                "processing_orders": Order.objects.filter(
                    status__in=[
                        Order.Status.CONFIRMED,
                        Order.Status.PROCESSING,
                        Order.Status.IN_PROGRESS,
                        Order.Status.ON_WAY,
                    ]
                ).count(),
                "delivered_orders": Order.objects.filter(
                    status__in=[Order.Status.DELIVERED, Order.Status.RECEIVED]
                ).count(),
                "return_requests": ReturnRequest.objects.filter(
                    status=ReturnRequest.Status.REQUESTED
                ).count(),
                "total_sales": Order.objects.exclude(status=Order.Status.CANCELLED).aggregate(
                    total=Sum("grand_total")
                )["total"]
                or 0,
                "low_stock_products": Product.objects.filter(
                    is_active=True, stock_quantity__lte=F("min_stock_level")
                ).order_by("stock_quantity")[:8],
                "recent_orders": Order.objects.select_related("customer")[:8],
                "recent_grns": GRN.objects.select_related("vendor")[:8],
                "today": timezone.localdate(),
            }
        )
        return context
