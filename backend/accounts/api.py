from typing import Literal, Optional

import shutil

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from ninja import Router, Schema, Status
from ninja.errors import HttpError
from ninja.utils import check_csrf

from .models import User

router = Router(tags=["auth"])
me_router = Router(tags=["auth"])


class CsrfOut(Schema):
    csrf_token: str


class LoginIn(Schema):
    email: str
    password: str


class MeOut(Schema):
    id: str
    email: str
    display_name: str
    role: str
    locale: str


class MePatch(Schema):
    display_name: Optional[str] = None
    locale: Optional[Literal["es", "en"]] = None


class ErrorOut(Schema):
    detail: str


def _me(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "locale": user.locale,
    }


@router.get("/csrf", auth=None, response=CsrfOut)
def csrf(request):
    return {"csrf_token": get_token(request)}


@router.post("/login", auth=None, response={200: MeOut, 401: ErrorOut, 403: ErrorOut, 429: ErrorOut})
def login_view(request, payload: LoginIn):
    if check_csrf(request) is not None:
        return Status(403, {"detail": "csrf_failed"})
    user = authenticate(request, username=payload.email, password=payload.password)
    if getattr(request, "axes_locked_out", False):
        return Status(429, {"detail": "too_many_attempts"})
    if user is None:
        return Status(401, {"detail": "invalid_credentials"})
    login(request, user)
    return Status(200, _me(user))


@router.post("/logout", response={204: None})
def logout_view(request):
    logout(request)
    return Status(204, None)


@me_router.get("", response=MeOut)
def me(request):
    return _me(request.user)


@me_router.patch("", response=MeOut)
def update_me(request, payload: MePatch):
    user = request.user
    data = payload.dict(exclude_unset=True, exclude_none=True)
    if "display_name" in data:
        name = data["display_name"].strip()
        if not name or len(name) > 100:
            raise HttpError(422, "invalid_display_name")
        user.display_name = name
    if "locale" in data:
        user.locale = data["locale"]
    user.save(update_fields=["display_name", "locale"])
    return _me(user)


class PasswordIn(Schema):
    current_password: str
    new_password: str


class DeleteIn(Schema):
    password: str


@me_router.post("/password", response={204: None, 400: ErrorOut, 403: ErrorOut})
def change_password(request, payload: PasswordIn):
    user = request.user
    if not user.check_password(payload.current_password):
        return Status(403, {"detail": "wrong_password"})
    try:
        validate_password(payload.new_password, user)
    except ValidationError as exc:
        return Status(400, {"detail": " ".join(exc.messages)})
    user.set_password(payload.new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)
    return Status(204, None)


@me_router.post("/delete", response={204: None, 403: ErrorOut, 409: ErrorOut})
def delete_account(request, payload: DeleteIn):
    """Borra la cuenta y todos sus datos; los lugares que propuso quedan sin autor."""
    from visits import media as storage

    user = request.user
    if not user.check_password(payload.password):
        return Status(403, {"detail": "wrong_password"})
    if user.role == User.Role.ADMIN and not User.objects.filter(role=User.Role.ADMIN, is_active=True).exclude(
        id=user.id
    ).exists():
        return Status(409, {"detail": "last_admin"})
    user_dir = storage.media_root() / str(user.id)
    with transaction.atomic():
        logout(request)
        user.delete()
    shutil.rmtree(user_dir, ignore_errors=True)
    return Status(204, None)
