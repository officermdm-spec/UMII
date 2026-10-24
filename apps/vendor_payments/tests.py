from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.accounting.models import AccountingPosting, JournalEntry, VendorPayment
from apps.vendor_payments.services import record_vendor_payment, void_vendor_payment
from apps.vendors.models import Vendor

User = get_user_model()


class VendorPaymentModuleTests(TestCase):
    def setUp(self):
        self.warehouse, self.category, self.vendor, self.product = build_catalog()
        self.staff = User.objects.create_user(
            username="ap",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.VENDOR_PAYMENTS],
        )
        self.reader = User.objects.create_user(
            username="reader",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.VENDOR_PAYMENTS],
            access_mode=User.AccessMode.VIEWER,
        )

    def test_staff_can_post_and_void_vendor_payment(self):
        self.client.login(username="ap", password="pass12345")
        response = self.client.get(reverse("vendor_payments:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Print")
        posted = self.client.post(
            reverse("vendor_payments:create"),
            {
                "vendor": self.vendor.pk,
                "amount": "150.00",
                "date": "2026-09-23",
                "payment_account": "cash",
                "reference": "CHQ-1",
                "notes": "",
            },
        )
        self.assertEqual(posted.status_code, 302)
        payment = VendorPayment.objects.get()
        self.assertEqual(payment.status, VendorPayment.Status.POSTED)
        self.assertTrue(AccountingPosting.objects.filter(event_key=f"vendor_payment:{payment.pk}").exists())
        voided = self.client.post(reverse("vendor_payments:void", args=[payment.pk]))
        self.assertEqual(voided.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, VendorPayment.Status.VOID)
        original = AccountingPosting.objects.get(event_key=f"vendor_payment:{payment.pk}").journal
        self.assertEqual(original.status, JournalEntry.Status.REVERSED)

    def test_old_accounting_payables_url_redirects(self):
        self.client.login(username="ap", password="pass12345")
        response = self.client.get(reverse("accounting:payables"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("vendor_payments:list"))

    def test_viewer_cannot_post_vendor_payment(self):
        self.client.login(username="reader", password="pass12345")
        self.assertEqual(self.client.get(reverse("vendor_payments:list")).status_code, 200)
        response = self.client.post(
            reverse("vendor_payments:create"),
            {
                "vendor": self.vendor.pk,
                "amount": "10.00",
                "date": "2026-09-23",
                "payment_account": "cash",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(VendorPayment.objects.exists())

    def test_service_does_not_duplicate_ledger_on_void(self):
        payment = VendorPayment(vendor=self.vendor, amount=Decimal("25.00"), payment_account="cash")
        record_vendor_payment(payment, self.staff)
        void_vendor_payment(payment, self.staff)
        self.assertEqual(VendorPayment.objects.filter(status=VendorPayment.Status.POSTED).count(), 0)
        self.assertEqual(AccountingPosting.objects.filter(event_key=f"vendor_payment:{payment.pk}").count(), 1)


class VendorSpecificPaymentTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(company_name="Acme", phone="03001111111")
        self.staff = User.objects.create_user(
            username="vendor-ap",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.VENDORS, MODULES.VENDOR_PAYMENTS],
        )
        self.client.login(username="vendor-ap", password="pass12345")

    def test_vendor_detail_has_vendor_specific_payment_flow(self):
        form_url = reverse("vendor_payments:vendor_create", args=[self.vendor.pk])
        response = self.client.get(form_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="vendor"')
        self.assertNotContains(response, "Notes")
        self.assertNotContains(response, '<select name="vendor"', html=False)

        response = self.client.post(
            form_url,
            {
                "vendor": self.vendor.pk,
                "amount": "150.00",
                "date": "2026-09-23",
                "payment_account": "cash",
                "reference": "CHQ-1",
            },
        )
        payment = VendorPayment.objects.get()
        self.assertEqual(payment.vendor, self.vendor)
        self.assertEqual(response.url, reverse("vendors:detail", args=[self.vendor.pk]))

        detail = self.client.get(response.url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Record payment")
        self.assertContains(detail, "150.00")

    def test_general_payment_form_redirects_to_payment_list(self):
        response = self.client.post(
            reverse("vendor_payments:create"),
            {
                "vendor": self.vendor.pk,
                "amount": "75.00",
                "date": "2026-09-23",
                "payment_account": "cash",
                "reference": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("vendor_payments:list"))

    def test_vendor_payment_list_and_search_use_vendor_company_name(self):
        payment = VendorPayment.objects.create(
            vendor=self.vendor,
            amount=Decimal("50.00"),
            payment_account="cash",
        )
        response = self.client.get(reverse("vendor_payments:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme")

        response = self.client.get(reverse("vendor_payments:list"), {"q": "Acme"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(payment.pk))
