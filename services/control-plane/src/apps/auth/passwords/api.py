from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth.otp.challenges import send_otp, verify_otp
from apps.auth.passwords.updates import complete_password_update
from apps.auth.sessions.cookies import verify_auth_security_headers
from apps.auth.throttles import PasswordChangeRateThrottle


class PasswordChangeRequestEndpoint(APIView):
    throttle_classes = (PasswordChangeRateThrottle,)

    def post(self, request):
        send_otp(email=request.user.email, purpose="password_change")
        return Response({"message": "Verification code sent."})


class PasswordChangeVerifyEndpoint(APIView):
    throttle_classes = (PasswordChangeRateThrottle,)

    def post(self, request):
        token = verify_otp(
            email=request.user.email,
            code=str(request.data.get("otp_code", "")),
            purpose="password_change",
        )
        return Response({"message": "Verification code accepted.", "password_change_token": token})


class PasswordChangeCompleteEndpoint(APIView):
    def post(self, request):
        if request.headers.get("Origin") or request.headers.get("X-Requested-With"):
            verify_auth_security_headers(request)

        return complete_password_update(
            str(request.data.get("password_change_token", "")),
            str(request.data.get("new_password", "")),
            actor=request.user,
        )
