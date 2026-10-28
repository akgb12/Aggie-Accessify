from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

DEFAULT_PREFERENCES: dict[str, object] = {
    "default_effort": "medium",
    "show_demo_options": False,
}


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
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
