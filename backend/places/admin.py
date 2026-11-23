from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import Category, OsmImport, Place, PlaceCategory


class PlaceCategoryInline(admin.TabularInline):
    model = PlaceCategory
    extra = 0
    autocomplete_fields = ["category"]


@admin.register(Place)
class PlaceAdmin(GISModelAdmin):
    list_display = ["display_name", "name_romaji", "kind", "prefecture", "status", "source", "osm_missing"]
    list_filter = ["kind", "status", "source", "osm_missing", "prefecture__region", "prefecture"]
    search_fields = ["name_ja", "name_romaji", "name_en", "alt_names"]
    autocomplete_fields = ["merged_into", "created_by"]
    readonly_fields = ["created_at", "updated_at", "osm_type", "osm_id"]
    inlines = [PlaceCategoryInline]
    actions = ["approve", "reject"]

    def save_model(self, request, obj, form, change):
        if change and obj.source == "osm":
            obj.locally_modified = True
        super().save_model(request, obj, form, change)

    @admin.action(description="Aprobar lugares seleccionados")
    def approve(self, request, queryset):
        queryset.filter(status__in=["pending", "rejected"]).update(status="approved")

    @admin.action(description="Rechazar lugares seleccionados")
    def reject(self, request, queryset):
        queryset.filter(status="pending").update(status="rejected")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["slug", "type", "name_es", "name_en", "total_items"]
    list_filter = ["type"]
    search_fields = ["slug", "name_es", "name_en", "name_ja"]


@admin.register(OsmImport)
class OsmImportAdmin(admin.ModelAdmin):
    list_display = ["region", "status", "requested_at", "finished_at", "total", "created", "updated", "linked", "missing"]
    list_filter = ["status", "region"]
    readonly_fields = [f.name for f in OsmImport._meta.fields]

    def has_add_permission(self, request):
        return False
