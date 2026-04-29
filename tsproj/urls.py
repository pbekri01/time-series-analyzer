from django.contrib import admin
from django.urls import path, include
from analysis_app.views import upload_page

urlpatterns = [
    path("", upload_page),
    path("admin/", admin.site.urls),
    path("api/", include("analysis_app.urls")),
]
