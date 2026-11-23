from django.contrib import admin, messages
from django.contrib.gis.admin import GISModelAdmin
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import Category, OsmImport, Place, PlaceCategory, PlaceCorrection, PlaceReview, ReviewStatus
from .services import CorrectionError, MergeError, apply_correction, merge_candidates, merge_place, reject_correction


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


def _current_value(place, field):
    if field == "lat":
        return round(place.location.y, 6) if place.location else None
    if field == "lon":
        return round(place.location.x, 6) if place.location else None
    if field == "prefecture_id":
        return place.prefecture
    if field == "area_id":
        return place.area
    return getattr(place, field, None)


@admin.register(PlaceCorrection)
class PlaceCorrectionAdmin(admin.ModelAdmin):
    list_display = ["place", "user", "created_at", "status", "summary"]
    list_filter = ["status"]
    list_select_related = ["place", "user"]
    search_fields = ["place__name_ja", "place__name_romaji", "place__name_en", "comment"]
    readonly_fields = ["place_link", "user", "created_at", "diff", "comment", "status", "reviewed_by", "reviewed_at"]
    fields = readonly_fields
    actions = ["apply_selected", "reject_selected"]
    change_form_template = "admin/places/correction_change_form.html"

    def has_add_permission(self, request):
        return False

    def response_change(self, request, obj):
        if "_apply" in request.POST:
            try:
                apply_correction(obj, request.user)
                self.message_user(request, f"Propuesta aplicada a {obj.place}.", messages.SUCCESS)
            except CorrectionError as e:
                self.message_user(request, str(e), messages.ERROR)
            return redirect("admin:places_placecorrection_changelist")
        if "_reject" in request.POST:
            reject_correction(obj, request.user)
            self.message_user(request, "Propuesta rechazada.", messages.SUCCESS)
            return redirect("admin:places_placecorrection_changelist")
        return super().response_change(request, obj)

    @admin.display(description="cambios")
    def summary(self, obj):
        return ", ".join(obj.changes) or "(solo comentario)"

    @admin.display(description="lugar")
    def place_link(self, obj):
        url = reverse("admin:places_place_change", args=[obj.place_id])
        return format_html('<a href="{}">{}</a>', url, obj.place)

    @admin.display(description="actual → propuesto")
    def diff(self, obj):
        if not obj.changes:
            return "(sin cambios de datos)"
        rows = format_html_join(
            "",
            "<tr><th>{}</th><td>{}</td><td><b>{}</b></td></tr>",
            ((f, _current_value(obj.place, f) if _current_value(obj.place, f) not in (None, "") else "—",
              v if v not in (None, "") else "—") for f, v in obj.changes.items()),
        )
        return format_html("<table><tr><th>campo</th><th>actual</th><th>propuesto</th></tr>{}</table>", rows)

    @admin.action(description="Aplicar propuestas seleccionadas")
    def apply_selected(self, request, queryset):
        done = 0
        for c in queryset.filter(status=PlaceCorrection.Status.PENDING):
            try:
                apply_correction(c, request.user)
                done += 1
            except CorrectionError as e:
                self.message_user(request, f"{c.place}: {e}", messages.ERROR)
        self.message_user(request, f"{done} propuesta(s) aplicada(s).", messages.SUCCESS)

    @admin.action(description="Rechazar propuestas seleccionadas")
    def reject_selected(self, request, queryset):
        n = sum(reject_correction(c, request.user) for c in queryset.filter(status=PlaceCorrection.Status.PENDING))
        self.message_user(request, f"{n} propuesta(s) rechazada(s).", messages.SUCCESS)
