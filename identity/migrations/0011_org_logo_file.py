from django.db import migrations, models

import identity.models


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0010_person_avatar_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="org",
            name="logo_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=identity.models.org_logo_upload_to,
            ),
        ),
    ]
