import json


def axes_username(request, credentials):
    """Usuario para django-axes: email normalizado, venga del login de la API (JSON) o del admin."""
    username = None
    if credentials:
        username = credentials.get("username") or credentials.get("email")
    if not username and request is not None:
        username = request.POST.get("username") or request.POST.get("email")
        if not username and request.content_type == "application/json":
            try:
                username = json.loads(request.body or b"{}").get("email")
            except (ValueError, AttributeError):
                username = None
    return (username or "").strip().lower() or None
