from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import User


class UserCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "display_name", "role")


class UserEditForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {"email": forms.EmailField}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserEditForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "display_name", "role", "locale", "is_active", "last_login")
    list_filter = ("role", "is_active", "locale")
    search_fields = ("email", "display_name")
    readonly_fields = ("created_at", "last_login")
    filter_horizontal = ()
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Perfil", {"fields": ("display_name", "locale", "oidc_subject")}),
        ("Acceso", {"fields": ("role", "is_active")}),
        ("Fechas", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "display_name", "role", "password1", "password2")}),
    )
