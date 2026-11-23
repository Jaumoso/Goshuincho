from django.contrib.gis.db import models


class Region(models.Model):
    id = models.SmallIntegerField(primary_key=True)
    slug = models.SlugField(unique=True)
    name_ja = models.TextField()
    name_en = models.TextField()
    name_es = models.TextField()

    class Meta:
        db_table = "regions"
        ordering = ["id"]
        verbose_name = "región"
        verbose_name_plural = "regiones"

    def __str__(self):
        return self.name_es


class Prefecture(models.Model):
    id = models.SmallIntegerField(primary_key=True, help_text="Código JIS X 0401 (1..47)")
    iso_code = models.CharField(max_length=5, unique=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="prefectures")
    name_ja = models.TextField()
    name_romaji = models.TextField()
    name_en = models.TextField()
    name_es = models.TextField()
    centroid = models.PointField(geography=True, srid=4326, null=True, blank=True)
    boundary = models.MultiPolygonField(srid=4326, null=True, blank=True)

    class Meta:
        db_table = "prefectures"
        ordering = ["id"]
        verbose_name = "prefectura"

    def __str__(self):
        return self.name_es


class Area(models.Model):
    prefecture = models.ForeignKey(Prefecture, on_delete=models.PROTECT, related_name="areas")
    slug = models.SlugField(unique=True)
    name_ja = models.TextField(null=True, blank=True)
    name_en = models.TextField()
    name_es = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "areas"
        ordering = ["prefecture_id", "name_en"]
        verbose_name = "zona"

    def __str__(self):
        return self.name_es or self.name_en
