import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import Q


class PlaceKind(models.TextChoices):
    SHRINE = "shrine", "santuario"
    TEMPLE = "temple", "templo"
    STATION = "station", "estación"
    SITE = "site", "otro sitio"


class ReviewStatus(models.TextChoices):
    APPROVED = "approved", "aprobado"
    PENDING = "pending", "pendiente"
    REJECTED = "rejected", "rechazado"
    MERGED = "merged", "fusionado"


class PlaceSource(models.TextChoices):
    OSM = "osm", "OpenStreetMap"
    CSV = "csv", "CSV"
    MANUAL = "manual", "manual"
    USER = "user", "usuario"


class Place(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.TextField(choices=PlaceKind.choices)
    name_ja = models.TextField(null=True, blank=True)
    name_romaji = models.TextField(null=True, blank=True)
    name_en = models.TextField(null=True, blank=True)
    name_romaji_generated = models.BooleanField(default=False)
    alt_names = ArrayField(models.TextField(), default=list, blank=True)
    tradition = models.TextField(null=True, blank=True)
    operator = models.TextField(null=True, blank=True)
    prefecture = models.ForeignKey("geo.Prefecture", on_delete=models.DO_NOTHING, related_name="places")
    area = models.ForeignKey(
        "geo.Area", on_delete=models.DO_NOTHING, null=True, blank=True, related_name="places"
    )
    address = models.TextField(null=True, blank=True)
    location = models.PointField(geography=True, srid=4326, null=True, blank=True)
    website = models.TextField(null=True, blank=True)
    goshuin_available = models.BooleanField(null=True, blank=True)
    goshuin_info = models.TextField(null=True, blank=True)
    osm_type = models.TextField(null=True, blank=True)
    osm_id = models.BigIntegerField(null=True, blank=True)
    osm_missing = models.BooleanField(default=False)
    locally_modified = models.BooleanField(default=False)
    source = models.TextField(choices=PlaceSource.choices, default=PlaceSource.MANUAL)
    status = models.TextField(choices=ReviewStatus.choices, default=ReviewStatus.APPROVED)
    merged_into = models.ForeignKey(
        "self", on_delete=models.DO_NOTHING, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DB_SET_NULL,
        null=True,
        blank=True,
        related_name="created_places",
    )
    categories = models.ManyToManyField("Category", through="PlaceCategory", related_name="places")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "places"
        verbose_name = "lugar"
        verbose_name_plural = "lugares"
        indexes = [models.Index(fields=["kind", "prefecture", "area"], name="places_filter_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(name_ja__isnull=False) | Q(name_romaji__isnull=False) | Q(name_en__isnull=False),
                name="places_has_name",
            ),
            models.CheckConstraint(
                condition=Q(status="merged", merged_into__isnull=False)
                | (~Q(status="merged") & Q(merged_into__isnull=True)),
                name="places_merged_into",
            ),
            models.CheckConstraint(condition=Q(kind__in=PlaceKind.values), name="places_kind"),
            models.CheckConstraint(condition=Q(status__in=ReviewStatus.values), name="places_status"),
            models.CheckConstraint(condition=Q(source__in=PlaceSource.values), name="places_source"),
            models.UniqueConstraint(
                fields=["osm_type", "osm_id"], condition=Q(osm_id__isnull=False), name="places_osm_uniq"
            ),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.name_ja or self.name_romaji or self.name_en or str(self.id)


class CategoryType(models.TextChoices):
    PILGRIMAGE = "pilgrimage", "ruta de peregrinaje"
    THEME = "theme", "tema"
    DEITY = "deity", "deidad"
    COLLECTION = "collection", "colección"


class Category(models.Model):
    slug = models.SlugField(unique=True)
    type = models.TextField(choices=CategoryType.choices)
    name_ja = models.TextField(null=True, blank=True)
    name_en = models.TextField()
    name_es = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    total_items = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "categories"
        ordering = ["type", "name_en"]
        verbose_name = "categoría"
        constraints = [models.CheckConstraint(condition=Q(type__in=CategoryType.values), name="categories_type")]

    def __str__(self):
        return self.name_es or self.name_en


class PlaceCategory(models.Model):
    pk = models.CompositePrimaryKey("place_id", "category_id")
    place = models.ForeignKey(Place, on_delete=models.DB_CASCADE)
    category = models.ForeignKey(Category, on_delete=models.DB_CASCADE)
    seq = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "place_categories"
        verbose_name = "lugar de la categoría"
        verbose_name_plural = "lugares de la categoría"


class UserPlace(models.Model):
    pk = models.CompositePrimaryKey("user_id", "place_id")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE)
    place = models.ForeignKey(Place, on_delete=models.DB_CASCADE)
    wishlist = models.BooleanField(default=False)
    favorite = models.BooleanField(default=False)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "user_places"


class OsmImport(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "en cola"
        RUNNING = "running", "en curso"
        DONE = "done", "terminada"
        FAILED = "failed", "fallida"

    region = models.ForeignKey("geo.Region", on_delete=models.CASCADE, related_name="osm_imports")
    status = models.TextField(choices=Status.choices, default=Status.QUEUED)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total = models.IntegerField(null=True, blank=True)
    created = models.IntegerField(null=True, blank=True)
    updated = models.IntegerField(null=True, blank=True)
    linked = models.IntegerField(null=True, blank=True)
    missing = models.IntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "osm_imports"
        ordering = ["-requested_at"]
        verbose_name = "importación de OpenStreetMap"
        verbose_name_plural = "importaciones de OpenStreetMap"

    def __str__(self):
        return f"{self.region} · {self.get_status_display()}"
