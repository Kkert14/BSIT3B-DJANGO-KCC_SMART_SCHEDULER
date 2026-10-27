import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('program', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Curriculum',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(max_length=150)),
                ('academic_year', models.CharField(max_length=9)),
                ('is_active', models.BooleanField(default=False)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='curricula', to='program.program')),
            ],
            options={
                'verbose_name': 'Curriculum',
                'verbose_name_plural': 'Curricula',
                'db_table': 'curricula',
                'ordering': ['-academic_year', 'code'],
                'unique_together': {('program', 'academic_year')},
            },
        ),
        migrations.CreateModel(
            name='Semester',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester_number', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(2)])),
                ('is_active', models.BooleanField(default=False)),
                ('curriculum', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='semesters', to='curriculum.curriculum')),
            ],
            options={
                'verbose_name': 'Semester',
                'verbose_name_plural': 'Semesters',
                'db_table': 'semesters',
                'ordering': ['curriculum', 'semester_number'],
                'unique_together': {('curriculum', 'semester_number')},
            },
        ),
    ]
