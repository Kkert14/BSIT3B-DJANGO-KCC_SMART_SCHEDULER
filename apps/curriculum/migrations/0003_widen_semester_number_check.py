from django.db import migrations


def _has_check(cursor, name):
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.CHECK_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'semesters'
          AND CONSTRAINT_NAME = %s
        """,
        [name],
    )
    return cursor.fetchone()[0] > 0


def widen_check(apps, schema_editor):
    """Allow semester_number 3 (Summer).

    The 1-2 CHECK constraint was created directly in the database, outside
    Django's migration state, so it has to be altered by hand.
    """
    if schema_editor.connection.vendor != 'mysql':
        return
    with schema_editor.connection.cursor() as cursor:
        if _has_check(cursor, 'ck_semesters_semester_number'):
            cursor.execute('ALTER TABLE semesters DROP CONSTRAINT ck_semesters_semester_number')
        cursor.execute(
            'ALTER TABLE semesters ADD CONSTRAINT ck_semesters_semester_number '
            'CHECK (semester_number BETWEEN 1 AND 3)'
        )


def narrow_check(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    with schema_editor.connection.cursor() as cursor:
        if _has_check(cursor, 'ck_semesters_semester_number'):
            cursor.execute('ALTER TABLE semesters DROP CONSTRAINT ck_semesters_semester_number')
        cursor.execute(
            'ALTER TABLE semesters ADD CONSTRAINT ck_semesters_semester_number '
            'CHECK (semester_number BETWEEN 1 AND 2)'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0002_alter_semester_semester_number'),
    ]

    operations = [
        migrations.RunPython(widen_check, narrow_check),
    ]
