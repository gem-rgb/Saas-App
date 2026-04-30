from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assignments", "0004_assignmentverification_assignmentverificationcheck_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="verification_rubric",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
