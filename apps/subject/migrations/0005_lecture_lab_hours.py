from django.db import migrations, models


def split_hours(apps, schema_editor):
    """Put the stored total on the side the lab flag indicated."""
    Subject = apps.get_model('subject', 'Subject')
    for subject in Subject.objects.all():
        subject.lecture_hours = 0 if subject.is_lab else subject.total_hours
        subject.lab_hours = subject.total_hours if subject.is_lab else 0
        subject.save(update_fields=['lecture_hours', 'lab_hours'])


def merge_hours(apps, schema_editor):
    """Fold the two hour types back into the old total plus lab flag."""
    Subject = apps.get_model('subject', 'Subject')
    for subject in Subject.objects.all():
        subject.total_hours = subject.lecture_hours + subject.lab_hours
        subject.is_lab = subject.lab_hours > 0
        subject.save(update_fields=['total_hours', 'is_lab'])


class Migration(migrations.Migration):

    dependencies = [
        ('subject', '0004_subject_total_hours_lab_flag'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='lecture_hours',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='subject',
            name='lab_hours',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(split_hours, merge_hours),
        migrations.RemoveField(
            model_name='subject',
            name='total_hours',
        ),
        migrations.RemoveField(
            model_name='subject',
            name='is_lab',
        ),
    ]
