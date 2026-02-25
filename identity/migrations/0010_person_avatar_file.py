from django.db import migrations, models

import identity.models


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0009_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="avatar_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=identity.models.person_avatar_upload_to,
            ),
        ),
    ]
