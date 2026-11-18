"""
Data migration: creates a default staff login so /staff/login/ works out of
the box on a fresh install, without needing `createsuperuser` first.

    username: staff
    password: 12345678

Skips creation if a user named "staff" already exists, so it is safe to run
twice and won't clobber a password someone already changed. Change or remove
this account before going to production with real orders.
"""
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations

STAFF_USERNAME = 'staff'
STAFF_PASSWORD = '12345678'


def seed_staff_user(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    if User.objects.filter(username=STAFF_USERNAME).exists():
        return  # already there — don't touch an existing/changed password
    User.objects.create(
        username=STAFF_USERNAME,
        password=make_password(STAFF_PASSWORD),
        is_staff=True,
        is_active=True,
        is_superuser=False,
    )


def unseed_staff_user(apps, schema_editor):
    # Reverse: remove only this exact seeded account.
    User = apps.get_model(settings.AUTH_USER_MODEL)
    User.objects.filter(username=STAFF_USERNAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_seed_dishes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_staff_user, reverse_code=unseed_staff_user),
    ]
