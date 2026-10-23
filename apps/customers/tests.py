from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.tests import build_catalog
from apps.customers.models import Address

User = get_user_model()


class CustomerPrivacyTests(TestCase):
    def setUp(self):
        build_catalog()
        self.user = User.objects.create_user(
            username="a", password="pass12345", user_type=User.UserType.CUSTOMER, email="a@example.com"
        )
        self.other = User.objects.create_user(
            username="b", password="pass12345", user_type=User.UserType.CUSTOMER, email="b@example.com"
        )
        self.address = Address.objects.create(
            user=self.other,
            full_name="Other",
            phone="03000000000",
            address="Hidden",
            city="Lahore",
        )

    def test_cannot_edit_someone_elses_address(self):
        self.client.login(username="a", password="pass12345")
        response = self.client.get(reverse("customers:address_update", args=[self.address.pk]))
        self.assertEqual(response.status_code, 404)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="officermdm@gmail.com",
)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="forgot",
            password="oldpass12345",
            user_type=User.UserType.CUSTOMER,
            email="forgot@example.com",
        )

    def test_login_pages_show_forgot_password(self):
        customer = self.client.get(reverse("customers:login"))
        staff = self.client.get(reverse("accounts:staff_login"))
        self.assertContains(customer, "Forgot password?")
        self.assertContains(staff, "Forgot password?")
        self.assertContains(customer, reverse("customers:password_reset"))

    def test_reset_email_sent_from_store_mailbox(self):
        response = self.client.post(
            reverse("customers:password_reset"), {"email": "forgot@example.com"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.from_email, "officermdm@gmail.com")
        self.assertEqual(message.to, ["forgot@example.com"])
        self.assertIn("password", message.subject.lower())
        self.assertTrue(message.alternatives)

    def test_unknown_email_does_not_leak_account(self):
        response = self.client.post(
            reverse("customers:password_reset"), {"email": "nobody@example.com"}
        )
        self.assertRedirects(response, reverse("customers:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_link_sets_new_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse("customers:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        page = self.client.get(url)
        self.assertEqual(page.status_code, 302)
        save = self.client.post(
            page["Location"],
            {"new_password1": "BrandNewPass123", "new_password2": "BrandNewPass123"},
        )
        self.assertEqual(save.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass123"))
        self.assertFalse(self.user.check_password("oldpass12345"))

    def test_smtp_failure_does_not_crash_reset(self):
        from smtplib import SMTPAuthenticationError
        from unittest.mock import patch

        with patch(
            "django.contrib.auth.forms.PasswordResetForm.send_mail",
            side_effect=SMTPAuthenticationError(535, b"bad credentials"),
        ):
            response = self.client.post(
                reverse("customers:password_reset"), {"email": "forgot@example.com"}
            )
        self.assertRedirects(response, reverse("customers:password_reset_done"))

    def test_reset_link_is_https_on_render(self):
        from unittest.mock import patch

        with patch.dict("os.environ", {"RENDER": "true"}):
            self.client.post(
                reverse("customers:password_reset"), {"email": "forgot@example.com"}
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://", mail.outbox[0].body)


class ResilientSMTPBackendTests(TestCase):
    def test_render_prefers_starttls_then_ssl(self):
        from unittest.mock import patch

        from config.email import ResilientSMTPBackend

        with patch.dict("os.environ", {"RENDER": "true"}):
            backend = ResilientSMTPBackend(
                host="smtp.gmail.com",
                port=465,
                username="u",
                password="p",
                use_ssl=True,
                use_tls=False,
            )
            self.assertEqual([item[0] for item in backend._attempts()], [465, 587])

    def test_falls_back_when_first_port_is_unreachable(self):
        from unittest.mock import MagicMock, patch

        from config.email import ResilientSMTPBackend

        backend = ResilientSMTPBackend(
            host="smtp.gmail.com",
            port=465,
            username="u",
            password="p",
            use_ssl=True,
            use_tls=False,
        )
        attempts = {"n": 0}

        def fake_open():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError(101, "Network is unreachable")
            backend.connection = MagicMock()
            return True

        with patch.dict("os.environ", {"RENDER": "true"}):
            with patch.object(backend, "_open_once", side_effect=fake_open):
                opened = backend.open()

        self.assertTrue(opened)
        self.assertEqual(backend.port, 587)
        self.assertEqual(attempts["n"], 2)


class HttpsEmailBackendTests(TestCase):
    @override_settings(EMAIL_HTTP_URL="", EMAIL_HTTP_SECRET="")
    def test_missing_bridge_fails_fast(self):
        from django.core.mail import EmailMessage

        from config.email import HttpsEmailBackend

        with self.assertRaises(OSError):
            HttpsEmailBackend().send_messages(
                [EmailMessage("s", "b", "a@b.com", ["c@d.com"])]
            )

    @override_settings(EMAIL_HTTP_URL="https://example.com/exec", EMAIL_HTTP_SECRET="abc")
    def test_posts_json_to_bridge(self):
        from unittest.mock import MagicMock, patch

        from django.core.mail import EmailMessage

        from config.email import HttpsEmailBackend

        response = MagicMock()
        response.read.return_value = b"ok"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        opener = MagicMock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            sent = HttpsEmailBackend().send_messages(
                [
                    EmailMessage(
                        "Reset",
                        "body",
                        "officermdm@gmail.com",
                        ["user@example.com"],
                    )
                ]
            )
        self.assertEqual(sent, 1)
        opener.open.assert_called_once()

