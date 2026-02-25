from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0009_client"),
        ("work_items", "0011_delete_projectclientaccess"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="projects",
                to="identity.client",
            ),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(
                fields=["org", "client"],
                name="wi_project_org_client_idx",
            ),
        ),
    ]
