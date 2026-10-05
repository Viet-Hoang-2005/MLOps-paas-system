from rest_framework import serializers


class ProductionDataQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, default=100, min_value=1, max_value=10000)
    version_id = serializers.UUIDField(required=False)
