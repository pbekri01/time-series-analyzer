from django.urls import path
from .views import AnalyzeCSVView, upload_page, map_fragment, chat_with_analysis, reset_chat
from . import views

urlpatterns = [
    path("", upload_page),
    path("analyze/", AnalyzeCSVView.as_view(), name="analyze"),
    path("map-fragment/", map_fragment, name="map_fragment"),
    path("chat/", chat_with_analysis, name="chat_with_analysis"),
    path("chat/reset/", reset_chat, name="reset_chat"),
    path("available-pairs/", views.available_pairs, name="available_pairs"),
]
