from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("work_items", "0012_project_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="actual_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="actual_ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subtask",
            name="actual_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subtask",
            name="actual_ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
