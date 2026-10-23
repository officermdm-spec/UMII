from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pass12345")

    def test_dashboard_requires_staff(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)

    def test_superuser_sees_dashboard(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total sales")
