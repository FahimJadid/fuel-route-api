from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import ErrorSerializer
from trips.models import Trip
from trips.serializers import TripRequestSerializer, TripSerializer
from trips.services import plan_trip


class TripListView(APIView):
    @extend_schema(
        summary="Plan a trip with cost-optimal fuel stops",
        request=TripRequestSerializer,
        responses={
            201: TripSerializer,
            400: ErrorSerializer,
            422: ErrorSerializer,
            503: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = TripRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = plan_trip(serializer.to_trip_request())
        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)


class TripDetailView(APIView):
    @extend_schema(
        summary="Fetch a previously planned trip",
        responses={200: TripSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, pk) -> Response:
        trip = get_object_or_404(Trip, pk=pk)
        return Response(TripSerializer(trip).data)
