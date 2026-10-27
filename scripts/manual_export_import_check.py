"""Manual smoke check for the Excel export/import feature.

Run it from the project root::

    .venv\\Scripts\\python scripts\\manual_export_import_check.py

This talks to the REAL development database, so it creates and removes a
handful of rows named ``SMOKE_*``. It is deliberately NOT named ``test_*`` so
that ``manage.py test`` never collects it.

The automated coverage lives in ``apps/utils/tests_roundtrip.py``.
"""

import io
import json
import os
import sys

import django
from openpyxl import Workbook

# Make sure the project root is importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.test import Client, override_settings  # noqa: E402

from apps.building.models import Building  # noqa: E402

SMOKE_CODES = ('SMOKE_A', 'SMOKE_B')


def find_admin():
    admin = User.objects.filter(is_superuser=True).order_by('id').first()
    if admin is None:
        raise SystemExit('No superuser found - create one before running this script.')
    return admin


def main():
    client = Client()
    client.force_login(find_admin())

    print('=' * 60)
    print('EXPORT / IMPORT SMOKE CHECK')
    print('=' * 60)

    with override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1']):
        # --- 1. Export ------------------------------------------------------
        print('\n1. Export')
        response = client.get('/buildings/export/excel/')
        print('   Status          :', response.status_code)
        print('   Content-Type    :', response.get('Content-Type'))
        print('   Content-Disposit:', response.get('Content-Disposition'))
        print('   Size            :', len(response.content), 'bytes')
        if response.status_code != 200:
            raise SystemExit('Export failed.')

        # --- 2. Re-import the file we just exported ------------------------
        print('\n2. Re-import the exported file (round trip)')
        response = client.post(
            '/buildings/import/excel/',
            {'file': io.BytesIO(response.content)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        payload = json.loads(response.content)
        print('   Status          :', response.status_code)
        print('   Created         :', payload.get('created'))
        print('   Errors          :', payload.get('errors') or 'none')
        if payload.get('errors'):
            raise SystemExit('Round trip reported errors.')

        # --- 3. Import a hand written file ---------------------------------
        print('\n3. Import a hand written file')
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Buildings'
        sheet.append(['code', 'name', 'is_active'])
        sheet.append([SMOKE_CODES[0], 'Smoke Building A', 'true'])
        sheet.append([SMOKE_CODES[1], 'Smoke Building B', 'false'])

        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        response = client.post(
            '/buildings/import/excel/',
            {'file': buffer},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        payload = json.loads(response.content)
        print('   Status          :', response.status_code)
        print('   Created         :', payload.get('created'))
        print('   Errors          :', payload.get('errors') or 'none')

        for code in SMOKE_CODES:
            building = Building.objects.filter(code=code).first()
            print(f'   {code} exists    :', building is not None,
                  '| name:', building.name if building else None,
                  '| active:', building.is_active if building else None)

        # --- 4. Clean up ---------------------------------------------------
        print('\n4. Clean up')
        deleted, _ = Building.objects.filter(code__in=SMOKE_CODES).delete()
        print('   Deleted rows    :', deleted)

    print('\n' + '=' * 60)
    print('SMOKE CHECK COMPLETE')
    print('=' * 60)


if __name__ == '__main__':
    main()
