from django.contrib import admin

from .models import Goshuincho, Media, Stamp, Visit


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ["place", "user", "kind", "visited_on", "visited_precision", "deleted_at"]
    list_filter = ["kind", "visited_precision"]
    search_fields = ["place__name_ja", "place__name_romaji", "user__email"]
    raw_id_fields = ["place", "user"]


@admin.register(Stamp)
class StampAdmin(admin.ModelAdmin):
    list_display = ["__str__", "user", "kind", "medium", "deleted_at"]
    list_filter = ["kind", "medium"]
    raw_id_fields = ["visit", "user", "place", "goshuincho"]


@admin.register(Goshuincho)
class GoshuinchoAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "started_on", "finished_on"]


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "mime", "bytes", "created_at"]
    readonly_fields = ["sha256", "storage_key", "variants"]
