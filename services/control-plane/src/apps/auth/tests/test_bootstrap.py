import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.auth.services.bootstrap import ensure_admin_account


@pytest.mark.django_db
def test_ensure_admin_account_creates_new_superuser():
    User = get_user_model()
    email = "superadmin@example.com"
    password = "supersecretpassword123"

    user, created = ensure_admin_account(email=email, password=password)

    assert created is True
    assert user is not None
    assert user.email == email
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.is_active is True
    assert user.check_password(password) is True
    assert User.objects.filter(email=email).count() == 1


@pytest.mark.django_db
def test_ensure_admin_account_preserves_existing_user():
    User = get_user_model()
    email = "existinguser@example.com"
    initial_password = "oldpassword123"

    # Create a normal non-staff user
    created_user = User.objects.create_user(email=email, password=initial_password)
    created_user.is_staff = False
    created_user.is_superuser = False
    created_user.save()

    user, created = ensure_admin_account(email=email, password="newpassword456")

    assert created is False
    assert user.id == created_user.id
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.is_active is True
    assert user.check_password(initial_password) is True
    assert user.check_password("newpassword456") is False


@pytest.mark.django_db
def test_bootstrap_command_requires_explicit_confirmation_to_update_existing_user():
    email = "existing-admin@example.com"
    old_password = "original-password123"
    user = get_user_model().objects.create_user(email=email, password=old_password)

    call_command("bootstrap_control_plane", email=email, password="replacement-password123")
    user.refresh_from_db()
    assert user.is_superuser is False
    assert user.check_password(old_password) is True

    call_command(
        "bootstrap_control_plane",
        email=email,
        password="replacement-password123",
        confirm_update_existing=True,
    )
    user.refresh_from_db()
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.check_password("replacement-password123") is True


@pytest.mark.django_db
def test_ensure_admin_account_reads_from_settings():
    email = "settingsadmin@example.com"
    password = "settingspassword123"

    with override_settings(ADMIN_EMAIL=email, ADMIN_PASSWORD=password):
        user, created = ensure_admin_account()

    assert created is True
    assert user is not None
    assert user.email == email
    assert user.check_password(password) is True


@pytest.mark.django_db
def test_ensure_admin_account_skips_when_empty_email():
    with override_settings(ADMIN_EMAIL="", ADMIN_PASSWORD="somepassword123"):
        user, created = ensure_admin_account()

    assert user is None
    assert created is False


@pytest.mark.django_db
def test_ensure_admin_account_skips_when_short_password():
    with override_settings(ADMIN_EMAIL="admin@example.com", ADMIN_PASSWORD="short"):
        user, created = ensure_admin_account()

    assert user is None
    assert created is False


@pytest.mark.django_db
def test_bootstrap_control_plane_command():
    email = "cliadmin@example.com"
    password = "clipassword123"

    call_command("bootstrap_control_plane", email=email, password=password)

    User = get_user_model()
    user = User.objects.get(email=email)
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.check_password(password) is True


@pytest.mark.django_db
def test_bootstrap_control_plane_command_empty_email(caplog):
    with override_settings(ADMIN_EMAIL="", ADMIN_PASSWORD=""):
        call_command("bootstrap_control_plane")

    assert any("ADMIN_EMAIL is empty" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_bootstrap_control_plane_command_short_password():
    with pytest.raises(CommandError, match="at least 8 characters"):
        call_command("bootstrap_control_plane", email="admin@example.com", password="123")
