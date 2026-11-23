from django.contrib.gis import admin

from .models import Area, Prefecture, Region


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("id", "name_es", "name_en", "name_ja", "slug", "last_osm_import")
    actions = ["import_osm"]

    @admin.display(description="última importación OSM")
    def last_osm_import(self, obj):
        job = obj.osm_imports.first()
        return f"{job.get_status_display()} · {job.requested_at:%Y-%m-%d %H:%M}" if job else "—"

    @admin.action(description="Importar de OpenStreetMap (en segundo plano)")
    def import_osm(self, request, queryset):
        from places.models import OsmImport
        from places.tasks import import_osm

        for region in queryset:
            job = OsmImport.objects.create(region=region)
            import_osm.defer(import_id=job.id)
        self.message_user(
            request,
            f"Importación encolada para {queryset.count()} región(es). "
            "Sigue el progreso en «Importaciones de OpenStreetMap».",
        )


@admin.register(Prefecture)
class PrefectureAdmin(admin.GISModelAdmin):
    list_display = ("id", "iso_code", "name_es", "name_romaji", "name_ja", "region")
    list_filter = ("region",)
    search_fields = ("name_es", "name_en", "name_romaji", "name_ja")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_es", "name_ja", "prefecture", "slug")
    list_filter = ("prefecture__region", "prefecture")
    search_fields = ("name_en", "name_es", "name_ja")
    prepopulated_fields = {"slug": ("name_en",)}
