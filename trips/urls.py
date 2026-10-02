from django.urls import path

from trips.views import TripDetailView, TripListView, TripMapView

urlpatterns = [
    path("trips/", TripListView.as_view(), name="trip-list"),
    path("trips/<uuid:pk>/", TripDetailView.as_view(), name="trip-detail"),
    path("trips/<uuid:pk>/map/", TripMapView.as_view(), name="trip-map"),
]
