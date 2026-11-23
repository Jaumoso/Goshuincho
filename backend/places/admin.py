from django.contrib import admin, messages
from django.contrib.gis.admin import GISModelAdmin
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import Category, OsmImport, Place, PlaceCategory, PlaceReview, ReviewStatus
from .services import MergeError, merge_candidates, merge_place


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
        target = obj.merged_into
        if change and target and "merged_into" in form.changed_data:
            # Elegir «fusionado en» en el formulario ejecuta la fusión completa.
            original = Place.objects.get(pk=obj.pk)
            obj.merged_into, obj.status = original.merged_into, original.status
            super().save_model(request, obj, form, change)
            try:
                merge_place(obj, target)
            except MergeError as e:
                self.message_user(request, str(e), messages.ERROR)
            return
        super().save_model(request, obj, form, change)

    @admin.action(description="Aprobar lugares seleccionados")
    def approve(self, request, queryset):
        queryset.filter(status__in=["pending", "rejected"]).update(status="approved")

    @admin.action(description="Rechazar lugares seleccionados")
    def reject(self, request, queryset):
        queryset.filter(status="pending").update(status="rejected")


@admin.register(PlaceReview)
class PlaceReviewAdmin(admin.ModelAdmin):
    """Cola de revisión: lugares propuestos por usuarios, con posibles duplicados para fusionar."""

    list_display = ["display_name", "name_romaji", "kind", "prefecture", "created_by", "created_at", "visit_count", "candidates"]
    list_filter = ["kind", "prefecture__region"]
    search_fields = ["name_ja", "name_romaji", "name_en"]
    ordering = ["created_at"]
    actions = ["approve", "reject"]
    list_display_links = ["display_name"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .filter(status=ReviewStatus.PENDING)
            .select_related("prefecture", "created_by")
            .annotate(n_visits=Count("visits", filter=Q(visits__deleted_at__isnull=True)))
        )

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return redirect(reverse("admin:places_place_change", args=[object_id]))

    @admin.display(description="visitas", ordering="n_visits")
    def visit_count(self, obj):
        return obj.n_visits

    @admin.display(description="¿duplicado de…? (fusionar)")
    def candidates(self, obj):
        found = merge_candidates(obj)
        if not found:
            return "—"
        return format_html_join(
            mark_safe("<br>"),
            '<a href="{}">→ {}</a> <small>{}</small>',
            (
                (
                    reverse("admin:places_placereview_merge", args=[obj.pk, c.pk]),
                    c.display_name,
                    f"{round(c.distance.m)} m" if getattr(c, "distance", None) is not None else "",
                )
                for c in found
            ),
        )

    @admin.action(description="Aprobar lugares seleccionados")
    def approve(self, request, queryset):
        n = queryset.update(status=ReviewStatus.APPROVED)
        self.message_user(request, f"{n} lugar(es) aprobado(s).")

    @admin.action(description="Rechazar lugares seleccionados")
    def reject(self, request, queryset):
        n = queryset.update(status=ReviewStatus.REJECTED)
        self.message_user(request, f"{n} lugar(es) rechazado(s).")

    def get_urls(self):
        view = self.admin_site.admin_view(self.merge_view)
        return [path("<uuid:source_id>/merge/<uuid:target_id>/", view, name="places_placereview_merge"), *super().get_urls()]

    def merge_view(self, request, source_id, target_id):
        source = get_object_or_404(Place, pk=source_id)
        target = get_object_or_404(Place, pk=target_id)
        back = reverse("admin:places_placereview_changelist")
        if not self.has_change_permission(request):
            return redirect(back)
        if request.method == "POST":
            try:
                merge_place(source, target)
            except MergeError as e:
                self.message_user(request, str(e), messages.ERROR)
            else:
                self.message_user(request, format_html("Fusionado en <strong>{}</strong>.", target.display_name))
            return redirect(back)
        distance = None
        if source.location and target.location:
            d = Place.objects.filter(pk=target.pk).annotate(d=Distance("location", source.location)).get().d
            distance = round(d.m)
        context = {
            **self.admin_site.each_context(request),
            "title": "Fusionar lugar",
            "source": source,
            "target": target,
            "visits": source.visits.filter(deleted_at__isnull=True).count(),
            "distance": distance,
            "back": back,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/places/merge_confirm.html", context)


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
