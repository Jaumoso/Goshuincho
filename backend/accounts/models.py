import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def normalize_email_address(email):
        return (email or "").strip().lower()

    def get_by_natural_key(self, username):
        return self.get(email=self.normalize_email_address(username))

    def create_user(self, email, password=None, **extra):
        email = self.normalize_email_address(email)
        if not email:
            raise ValueError("El email es obligatorio")
        extra.setdefault("display_name", email.split("@")[0])
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra["role"] = User.Role.ADMIN
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        USER = "user", "Usuario"

    class Locale(models.TextChoices):
        ES = "es", "Español"
        EN = "en", "English"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=100)
    oidc_subject = models.TextField(unique=True, null=True, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)
    locale = models.CharField(max_length=5, choices=Locale.choices, default=Locale.ES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "users"
        verbose_name = "usuario"

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_staff(self):
        return self.is_active and self.is_admin

    def clean(self):
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)

    def save(self, *args, **kwargs):
        self.email = UserManager.normalize_email_address(self.email)
        # El rol es la única fuente de permisos: el administrador tiene todos los del panel.
        self.is_superuser = self.is_admin
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role" in update_fields:
            kwargs["update_fields"] = {*update_fields, "is_superuser"}
        super().save(*args, **kwargs)
