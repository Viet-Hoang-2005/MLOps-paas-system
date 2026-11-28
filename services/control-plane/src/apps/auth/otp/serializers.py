from rest_framework import serializers


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class OTPSerializer(EmailSerializer):
    otp_code = serializers.RegexField(r"^\d{6}$")
