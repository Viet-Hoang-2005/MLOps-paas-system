# Durable watches for newly dispatched local Docker executions (no data backfill).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deployment', '0007_runtime_health'),
    ]

    operations = [
        migrations.AddField(
            model_name='build',
            name='callback_wait_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='build',
            name='execution_check_lease_until',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='build',
            name='execution_check_token',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='build',
            name='execution_deadline_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='build',
            name='next_execution_check_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='deployment',
            name='execution_check_lease_until',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='deployment',
            name='execution_check_token',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='deployment',
            name='execution_deadline_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='deployment',
            name='next_execution_check_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
