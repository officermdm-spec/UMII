from apps.accounts.models import StaffModule


MODULES = StaffModule

STAFF_NAV = [
    {"module": MODULES.DASHBOARD, "label": "Dashboard", "url_name": "dashboard:home", "namespace": "dashboard"},
    {"module": MODULES.USERS, "label": "Users & Permissions", "url_name": "accounts:user_list", "namespace": "accounts"},
    {"module": MODULES.CUSTOMERS, "label": "Customers", "url_name": "customers_staff:list", "namespace": "customers_staff"},
    {"module": MODULES.CATEGORIES, "label": "Categories", "url_name": "categories:list", "namespace": "categories"},
    {"module": MODULES.BRANDS, "label": "Brands", "url_name": "products:brand_list", "namespace": "products"},
    {"module": MODULES.PRODUCTS, "label": "Products", "url_name": "products:list", "namespace": "products"},
    {"module": MODULES.VENDORS, "label": "Vendors", "url_name": "vendors:list", "namespace": "vendors"},
    {"module": MODULES.GRN, "label": "GRN", "url_name": "purchases:list", "namespace": "purchases"},
    {"module": MODULES.WAREHOUSES, "label": "Warehouses", "url_name": "inventory:warehouse_list", "namespace": "inventory"},
    {"module": MODULES.INVENTORY, "label": "Inventory", "url_name": "inventory:list", "namespace": "inventory"},
    {"module": MODULES.ORDERS, "label": "Orders", "url_name": "orders_staff:list", "namespace": "orders_staff"},
    {"module": MODULES.PAYMENTS, "label": "Payments", "url_name": "payments:list", "namespace": "payments"},
    {"module": MODULES.PAYMENT_METHODS, "label": "Payment Methods", "url_name": "payments:methods", "namespace": "payments"},
    {"module": MODULES.RETURNS, "label": "Returns", "url_name": "returns_staff:list", "namespace": "returns_staff"},
    {"module": MODULES.REVIEWS, "label": "Reviews", "url_name": "reviews_staff:list", "namespace": "reviews_staff"},
    {"module": MODULES.PROMOTIONS, "label": "Promotions", "url_name": "promotions:list", "namespace": "promotions"},
    {"module": MODULES.ACCOUNTING, "label": "Accounting", "url_name": "accounting:dashboard", "namespace": "accounting"},
    {"module": MODULES.EXPENSES, "label": "Expenses", "url_name": "accounting:expenses", "namespace": "accounting"},
    {
        "module": MODULES.VENDOR_PAYMENTS,
        "label": "Vendor Payments",
        "url_name": "vendor_payments:list",
        "namespace": "vendor_payments",
    },
]

SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_staff_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.user_type == user.UserType.STAFF)
    )


def is_admin_user(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def has_module_permission(user, module):
    if not is_staff_user(user):
        return False
    if user.is_superuser:
        return True
    return module in (user.allowed_modules or [])


def is_read_only_staff(user):
    if not is_staff_user(user) or user.is_superuser:
        return False
    return getattr(user, "access_mode", "full") == "viewer"


def can_write(user):
    return is_staff_user(user) and not is_read_only_staff(user)


def nav_modules_for_user(user):
    if not is_staff_user(user):
        return []
    if user.is_superuser:
        return [dict(item) for item in STAFF_NAV]
    allowed = set(user.allowed_modules or [])
    return [dict(item) for item in STAFF_NAV if item["module"] in allowed]
