from django.urls import path

from trips.views import TripDetailView, TripListView

urlpatterns = [
    path("trips/", TripListView.as_view(), name="trip-list"),
    path("trips/<uuid:pk>/", TripDetailView.as_view(), name="trip-detail"),
]
