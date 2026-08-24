from .models import CustomUser


def active_user_by_email(email):
    return CustomUser.objects.filter(email__iexact=email, is_active=True).first()
