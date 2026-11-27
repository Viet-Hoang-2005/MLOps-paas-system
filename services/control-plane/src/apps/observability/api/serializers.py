from rest_framework import serializers


class ProductionDataQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, default=100, min_value=1, max_value=500)
    offset = serializers.IntegerField(required=False, default=0, min_value=0)
    version_id = serializers.UUIDField(required=False)
    count = serializers.BooleanField(required=False, default=False)
