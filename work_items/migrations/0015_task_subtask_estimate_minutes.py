from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("work_items", "0014_task_sow_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="estimate_minutes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subtask",
            name="estimate_minutes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
