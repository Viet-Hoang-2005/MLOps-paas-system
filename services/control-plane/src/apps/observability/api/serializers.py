from rest_framework import serializers


class ProductionDataQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, min_value=1)
