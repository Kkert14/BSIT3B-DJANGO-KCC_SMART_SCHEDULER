import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0001_initial'),
        ('schedule', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='schedule',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='schedule',
            name='academic_year',
        ),
        migrations.RemoveField(
            model_name='schedule',
            name='semester',
        ),
        migrations.AddField(
            model_name='schedule',
            name='semester',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='schedules',
                to='curriculum.semester',
            ),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='semester',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='schedules',
                to='curriculum.semester',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='schedule',
            unique_together={
                ('teacher', 'semester', 'day_of_week', 'start_time'),
                ('room', 'semester', 'day_of_week', 'start_time'),
                ('section', 'semester', 'day_of_week', 'start_time'),
            },
        ),
    ]
