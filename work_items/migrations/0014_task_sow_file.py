from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import work_items.models


class Migration(migrations.Migration):
    dependencies = [
        ("work_items", "0013_task_actual_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="sow_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=work_items.models.task_sow_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="sow_original_filename",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="task",
            name="sow_content_type",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="task",
            name="sow_size_bytes",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="task",
            name="sow_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="task",
            name="sow_uploaded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="sow_uploaded_by_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uploaded_task_sows",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

