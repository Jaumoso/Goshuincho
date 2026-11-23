from django.contrib.gis import admin

from .models import Area, Prefecture, Region


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("id", "name_es", "name_en", "name_ja", "slug")


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
