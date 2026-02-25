from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("work_items", "0010_remove_manual_progress"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ProjectClientAccess",
        ),
    ]
