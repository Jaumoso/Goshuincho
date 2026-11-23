import ipaddress

from django.conf import settings


class TrustedProxyMiddleware:
    """Acepta X-Forwarded-For/-Proto solo si la conexión viene de un proxy de confianza.

    Corrige REMOTE_ADDR (lo usa django-axes para limitar intentos de login) y el esquema
    (https detrás de un proxy que termina TLS).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = [ipaddress.ip_network(n, strict=False) for n in settings.TRUSTED_PROXIES]

    def _trusted(self, addr):
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in net for net in self.networks)

    def __call__(self, request):
        meta = request.META
        if self._trusted(meta.get("REMOTE_ADDR", "")):
            proto = meta.get("HTTP_X_FORWARDED_PROTO", "").split(",")[0].strip().lower()
            if proto in {"http", "https"}:
                meta["wsgi.url_scheme"] = proto
            forwarded = [a.strip() for a in meta.get("HTTP_X_FORWARDED_FOR", "").split(",") if a.strip()]
            # La IP del cliente es la primera, empezando por la derecha, que no es un proxy de confianza.
            for addr in reversed(forwarded):
                if not self._trusted(addr):
                    meta["REMOTE_ADDR"] = addr
                    break
            else:
                if forwarded:
                    meta["REMOTE_ADDR"] = forwarded[0]
        return self.get_response(request)
