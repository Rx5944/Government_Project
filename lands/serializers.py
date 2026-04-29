from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import LandParcel

class LandParcelSerializer(GeoFeatureModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)
    alert_count = serializers.IntegerField(read_only=True)
    risk_score = serializers.FloatField(source='encroachment_risk_score', read_only=True)
    last_scan = serializers.DateTimeField(source='last_satellite_scan', read_only=True, format="%Y-%m-%d %H:%M")
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)

    class Meta:
        model = LandParcel
        geo_field = 'geom'
        fields = (
            'id', 'survey_number', 'district_name', 'taluk', 'village',
            'classification', 'status', 'area_sqm', 
            'latitude', 'longitude',
            'alert_count', 'risk_score', 'last_scan'
        )
