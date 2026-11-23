import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class VisitKind(models.TextChoices):
    IN_PERSON = "in_person", "en persona"
    MAIL = "mail", "por correo"
    EVENT = "event", "en un evento"


class DatePrecision(models.TextChoices):
    DAY = "day", "día"
    MONTH = "month", "mes"
    SEASON = "season", "estación"
    YEAR = "year", "año"
    UNKNOWN = "unknown", "desconocida"


class StampKind(models.TextChoices):
    GOSHUIN = "goshuin", "goshuin"
    GOSHUIN_LIMITED = "goshuin_limited", "goshuin limitado"
    GOSHUIN_SEASONAL = "goshuin_seasonal", "goshuin de temporada"
    STATION_STAMP = "station_stamp", "sello de estación"
    OTHER_STAMP = "other_stamp", "otro sello"


GOSHUIN_KINDS = (StampKind.GOSHUIN, StampKind.GOSHUIN_LIMITED, StampKind.GOSHUIN_SEASONAL)


class StampMedium(models.TextChoices):
    JIKIGAKI = "jikigaki", "jikigaki"
    KAKIOKI = "kakioki", "kakioki"
    STAMPED_PAPER = "stamped_paper", "solo sello"
    DIGITAL = "digital", "digital"
    OTHER = "other", "otro"


class Goshuincho(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="goshuincho")
    name = models.TextField()
    description = models.TextField(null=True, blank=True)
    started_on = models.DateField(null=True, blank=True)
    finished_on = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "goshuincho"
        verbose_name = "libreta"
        constraints = [models.UniqueConstraint(fields=["id", "user"], name="goshuincho_id_user_uniq")]

    def __str__(self):
        return self.name


class Visit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="visits")
    # Sin cascada: los lugares se fusionan, no se borran.
    place = models.ForeignKey("places.Place", on_delete=models.DO_NOTHING, related_name="visits")
    kind = models.TextField(choices=VisitKind.choices, default=VisitKind.IN_PERSON)
    event_location = models.TextField(null=True, blank=True)
    visited_on = models.DateField(null=True, blank=True)
    visited_precision = models.TextField(choices=DatePrecision.choices, default=DatePrecision.DAY)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    media = models.ManyToManyField("Media", through="VisitMedia", related_name="visits")

    class Meta:
        db_table = "visits"
        verbose_name = "visita"
        constraints = [
            models.UniqueConstraint(fields=["id", "user", "place"], name="visits_id_user_place_uniq"),
            models.CheckConstraint(condition=Q(kind__in=VisitKind.values), name="visits_kind"),
            models.CheckConstraint(
                condition=Q(visited_precision__in=DatePrecision.values), name="visits_precision_values"
            ),
            models.CheckConstraint(
                condition=Q(kind="event") | Q(event_location__isnull=True), name="visits_event_location"
            ),
            # La coherencia de visited_on con la precisión se comprueba con un CHECK en RunSQL.
        ]

    def __str__(self):
        return f"{self.place} · {self.visited_on or '?'}"


class Stamp(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # visit/user/place y goshuincho/user están protegidos por claves foráneas compuestas en RunSQL.
    visit = models.ForeignKey(
        Visit, on_delete=models.DO_NOTHING, db_constraint=False, related_name="stamps"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, db_constraint=False, related_name="+"
    )
    place = models.ForeignKey(
        "places.Place", on_delete=models.DO_NOTHING, db_constraint=False, related_name="stamps"
    )
    kind = models.TextField(choices=StampKind.choices, default=StampKind.GOSHUIN)
    medium = models.TextField(choices=StampMedium.choices, null=True, blank=True)
    title = models.TextField(null=True, blank=True)
    event_name = models.TextField(null=True, blank=True)
    donation_yen = models.IntegerField(null=True, blank=True)
    goshuincho = models.ForeignKey(
        Goshuincho,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        blank=True,
        related_name="stamps",
    )
    page_label = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    media = models.ManyToManyField("Media", through="StampMedia", related_name="stamps")

    class Meta:
        db_table = "stamps"
        verbose_name = "goshuin o sello"
        verbose_name_plural = "goshuin y sellos"
        indexes = [models.Index(fields=["user", "place"], name="stamps_user_place_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=StampKind.values), name="stamps_kind"),
            models.CheckConstraint(
                condition=Q(medium__isnull=True) | Q(medium__in=StampMedium.values), name="stamps_medium"
            ),
            models.CheckConstraint(
                condition=Q(donation_yen__isnull=True) | Q(donation_yen__gte=0), name="stamps_donation"
            ),
        ]

    def __str__(self):
        return self.title or f"{self.get_kind_display()} · {self.place_id}"


class Media(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="media")
    sha256 = models.CharField(max_length=64)
    mime = models.TextField()
    bytes = models.BigIntegerField()
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    storage_key = models.TextField()
    variants = models.JSONField(default=dict, blank=True)
    taken_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media"
        verbose_name = "imagen"
        verbose_name_plural = "imágenes"
        constraints = [models.UniqueConstraint(fields=["user", "sha256"], name="media_user_sha256_uniq")]


class MediaRole(models.TextChoices):
    FRONT = "front", "anverso"
    BACK = "back", "reverso"
    SCAN = "scan", "escaneo"
    DETAIL = "detail", "detalle"


class StampMedia(models.Model):
    pk = models.CompositePrimaryKey("stamp_id", "media_id")
    stamp = models.ForeignKey(Stamp, on_delete=models.DB_CASCADE)
    media = models.ForeignKey(Media, on_delete=models.DB_CASCADE)
    role = models.TextField(choices=MediaRole.choices, default=MediaRole.FRONT)
    position = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "stamp_media"
        constraints = [models.CheckConstraint(condition=Q(role__in=MediaRole.values), name="stamp_media_role")]


class VisitMedia(models.Model):
    pk = models.CompositePrimaryKey("visit_id", "media_id")
    visit = models.ForeignKey(Visit, on_delete=models.DB_CASCADE)
    media = models.ForeignKey(Media, on_delete=models.DB_CASCADE)
    position = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "visit_media"


class UserPlaceSummary(models.Model):
    """Vista user_place_summary (solo lectura)."""

    pk = models.CompositePrimaryKey("user_id", "place_id")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, db_constraint=False)
    place = models.ForeignKey("places.Place", on_delete=models.DO_NOTHING, db_constraint=False)
    visit_count = models.IntegerField()
    first_visit = models.DateField(null=True)
    last_visit = models.DateField(null=True)
    last_visit_precision = models.TextField(null=True)
    stamp_count = models.IntegerField()

    class Meta:
        managed = False
        db_table = "user_place_summary"


def new_share_token() -> str:
    import secrets

    return secrets.token_urlsafe(24)


class ShareLink(models.Model):
    """Enlace público de solo lectura a la colección de goshuin (entera o de una libreta)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="share_links")
    token = models.TextField(unique=True, default=new_share_token)
    goshuincho = models.ForeignKey(
        Goshuincho, null=True, blank=True, on_delete=models.DB_CASCADE, related_name="share_links"
    )
    title = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    view_count = models.IntegerField(default=0)

    class Meta:
        db_table = "share_links"
        verbose_name = "enlace compartido"
        verbose_name_plural = "enlaces compartidos"

    def __str__(self):
        return self.title or str(self.id)
