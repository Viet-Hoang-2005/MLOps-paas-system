from rest_framework import serializers
from rest_framework.exceptions import ValidationError


def validate_output_revision(value, *, required=True):
    if value is None and not required:
        return None
    if value is None:
        raise ValidationError({"output_revision": "This field is required."})

    field = serializers.IntegerField(min_value=1)
    try:
        return field.run_validation(value)
    except serializers.ValidationError as exc:
        raise ValidationError({"output_revision": exc.detail}) from exc
