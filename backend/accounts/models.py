from decimal import Decimal

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

DEFAULT_PREFERENCES: dict[str, object] = {
    "default_effort": "medium",
    "show_demo_options": False,
}

# Every account may spend this much on model calls in total until someone raises its limit
DEFAULT_USAGE_LIMIT_USD = Decimal("20.00")


def default_preferences() -> dict[str, object]:
    # A fresh copy so accounts never share one dict
    return dict(DEFAULT_PREFERENCES)


class UserManager(BaseUserManager["User"]):
    def create_user(self, username: str, password: str | None = None, **fields: object) -> "User":
        # Usernames are stored lowercase so "AKanji" and "akanji" are one account
        user = self.model(username=username.strip().lower(), **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    # TAMU username for now; becomes the SSO identity once SAML/OIDC is approved
    username = models.CharField(max_length=32, unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    preferences = models.JSONField(default=default_preferences)
    # A hard cap on model spend, and what the account has spent. Spend is kept here rather
    # than summed from runs, so deleting projects does not give the money back.
    usage_limit_usd = models.DecimalField(
        max_digits=10, decimal_places=2, default=DEFAULT_USAGE_LIMIT_USD
    )
    spent_usd = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal(0))
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
