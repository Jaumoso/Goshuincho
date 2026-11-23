from django.contrib import admin
from django.urls import path, re_path

from .api import api
from .views import spa

admin.site.site_header = "Goshuinchō"
admin.site.site_title = "Goshuinchō"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    re_path(r"^(?!api/|admin/|static/|media/).*$", spa, name="spa"),
]
