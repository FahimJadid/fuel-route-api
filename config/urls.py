from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.views import UnknownEndpointView

urlpatterns = [
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("trips.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    re_path(r"^api/", UnknownEndpointView.as_view()),
]
