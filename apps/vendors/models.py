from django.db import models


class Vendor(models.Model):
    company_name = models.CharField(max_length=200, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    tax_ntn = models.CharField("Tax / NTN", max_length=50, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account = models.CharField(max_length=80, blank=True)
    iban = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"] 
        indexes = [
            models.Index(
                fields=["company_name"]
            ), 
            models.Index(fields=["city"]),
            models.Index(fields=["is_active"]),
        ]
    def __str__(self):
        return self.company_name
