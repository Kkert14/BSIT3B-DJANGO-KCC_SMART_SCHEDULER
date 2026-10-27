import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0001_initial'),
        ('subject', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='subject',
            unique_together={('program', 'code')},
        ),
        migrations.RemoveField(
            model_name='subject',
            name='academic_year',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='semester',
        ),
        migrations.AddField(
            model_name='subject',
            name='semester',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='subjects',
                to='curriculum.semester',
            ),
        ),
        migrations.AlterField(
            model_name='subject',
            name='semester',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='subjects',
                to='curriculum.semester',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='subject',
            unique_together={('program', 'code', 'semester')},
        ),
    ]
