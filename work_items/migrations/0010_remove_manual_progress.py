from __future__ import annotations

from django.db import migrations, models


def forwards(apps, schema_editor) -> None:
    Project = apps.get_model("work_items", "Project")
    Epic = apps.get_model("work_items", "Epic")
    Task = apps.get_model("work_items", "Task")

    Project.objects.filter(progress_policy="manual").update(progress_policy="workflow_stage")
    Epic.objects.filter(progress_policy="manual").update(progress_policy=None)
    Task.objects.filter(progress_policy="manual").update(progress_policy=None)


class Migration(migrations.Migration):
    dependencies = [
        ("work_items", "0009_merge_0007_project_client_access_0008_task_participants"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="progress_policy",
            field=models.CharField(
                choices=[
                    ("subtasks_rollup", "Subtasks rollup"),
                    ("workflow_stage", "Workflow stage"),
                ],
                default="subtasks_rollup",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="epic",
            name="progress_policy",
            field=models.CharField(
                blank=True,
                choices=[
                    ("subtasks_rollup", "Subtasks rollup"),
                    ("workflow_stage", "Workflow stage"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="progress_policy",
            field=models.CharField(
                blank=True,
                choices=[
                    ("subtasks_rollup", "Subtasks rollup"),
                    ("workflow_stage", "Workflow stage"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.RemoveField(
            model_name="epic",
            name="manual_progress_percent",
        ),
        migrations.RemoveField(
            model_name="task",
            name="manual_progress_percent",
        ),
    ]
