import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0001_initial'),
        ('section', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='section',
            unique_together={('program', 'year_level', 'name')},
        ),
        migrations.RemoveField(
            model_name='section',
            name='academic_year',
        ),
        migrations.AddField(
            model_name='section',
            name='semester',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='sections',
                to='curriculum.semester',
            ),
        ),
        migrations.AlterField(
            model_name='section',
            name='semester',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='sections',
                to='curriculum.semester',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='section',
            unique_together={('semester', 'program', 'year_level', 'name')},
        ),
    ]
