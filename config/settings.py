"""
Django settings for the E-commerce Management System.
Values that change between environments are loaded from `.env`.
"""
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import os
from decimal import Decimal
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")
# Render sets RENDER=true. Default DEBUG off there so the service does not run in debug mode.
DEBUG = env_bool("DEBUG", default=not bool(os.getenv("RENDER")))


def env_list(name, default=""):
    return [part.strip() for part in os.getenv(name, default).split(",") if part.strip()]


ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,ecommerce-ms-lz72.onrender.com")
_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts.apps.AccountsConfig",
    "apps.customers.apps.CustomersConfig",
    "apps.categories.apps.CategoriesConfig",
    "apps.vendors.apps.VendorsConfig",
    "apps.products.apps.ProductsConfig",
    "apps.inventory.apps.InventoryConfig",
    "apps.purchases.apps.PurchasesConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.returns.apps.ReturnsConfig",
    "apps.promotions.apps.PromotionsConfig",
    "apps.reviews.apps.ReviewsConfig",
    "apps.dashboard.apps.DashboardConfig",
    "apps.accounting.apps.AccountingConfig",
    "apps.vendor_payments.apps.VendorPaymentsConfig",
]

CLOUDINARY_STORAGE = {"PREFIX": ""}
_cloudinary_credentials = {
    "CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": os.getenv("CLOUDINARY_API_KEY"),
    "API_SECRET": os.getenv("CLOUDINARY_API_SECRET"),
}
if all(_cloudinary_credentials.values()):
    CLOUDINARY_STORAGE.update(_cloudinary_credentials)
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
                "config.context_processors.storefront",
                "config.context_processors.staff_nav",
            ],
        },
    }
]

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    DATABASE_URL = (
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'UMII')}"
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
    )
}


AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "config.storage.CatalogStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}


MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "customers:login"
LOGIN_REDIRECT_URL = "customers:dashboard"
LOGOUT_REDIRECT_URL = "store:home"
STAFF_LOGIN_URL = "accounts:staff_login"

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
# Render often cannot reach Gmail on 465/IPv6. 587 STARTTLS is the default there.
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587" if os.getenv("RENDER") else "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "officermdm@gmail.com")
EMAIL_HOST_PASSWORD = (
    (os.getenv("EMAIL_HOST_PASSWORD") or "")
    .strip()
    .strip('"')
    .strip("'")
    .replace(" ", "")
)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))
if os.getenv("RENDER"):
    EMAIL_TIMEOUT = min(EMAIL_TIMEOUT, 5)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
if EMAIL_PORT == 465:
    EMAIL_USE_SSL = True
    EMAIL_USE_TLS = False
else:
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_USE_SSL = False

EMAIL_HTTP_URL = (os.getenv("EMAIL_HTTP_URL") or "").strip()
EMAIL_HTTP_SECRET = (os.getenv("EMAIL_HTTP_SECRET") or "").strip()

_email_backend = (os.getenv("EMAIL_BACKEND") or "").strip()
if _email_backend.endswith("locmem.EmailBackend"):
    EMAIL_BACKEND = _email_backend
elif EMAIL_HTTP_URL:
    EMAIL_BACKEND = "config.email.HttpsEmailBackend"
elif os.getenv("RENDER"):
    # Gmail SMTP times out on Render. Do not hang workers trying 465/587.
    EMAIL_BACKEND = "config.email.HttpsEmailBackend"
elif EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "config.email.ResilientSMTPBackend"
else:
    EMAIL_BACKEND = _email_backend or "django.core.mail.backends.console.EmailBackend"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
# If False, a coupon cannot reduce a line that already has a product offer.
ALLOW_COUPON_WITH_PRODUCT_OFFER = env_bool("ALLOW_COUPON_WITH_PRODUCT_OFFER", False)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = ["https://ecommerce-ms-lz72.onrender.com"]
if _render_host:
    origin = f"https://{_render_host}"
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

STORE_NAME = os.getenv("STORE_NAME", "FP Mart")
STORE_PHONE = os.getenv("STORE_PHONE", "")
STORE_ADDRESS = os.getenv("STORE_ADDRESS", "")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "923002803733")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", DEFAULT_FROM_EMAIL)
SHIPPING_FLAT_RATE = Decimal(os.getenv("SHIPPING_FLAT_RATE", "150.00"))
TAX_PERCENT = Decimal(os.getenv("TAX_PERCENT", "0.00"))
CURRENCY = os.getenv("CURRENCY", "PKR")
DEFAULT_WAREHOUSE_CODE = os.getenv("DEFAULT_WAREHOUSE_CODE", "MAIN")
# Safe default: a checkout coupon does not stack on a line that already has a product offer.
ALLOW_COUPON_WITH_PRODUCT_OFFER = env_bool("ALLOW_COUPON_WITH_PRODUCT_OFFER", False)
