from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from django.conf import settings
from django.db.backends.sqlite3.base import DatabaseWrapper


@pytest.mark.django_db(transaction=True)
def test_local_atomic_writers_wait_then_preserve_both_updates(tmp_path):
    config = {**settings.DATABASES['default'], 'NAME': str(tmp_path / 'writers.sqlite3')}
    first = DatabaseWrapper(config)
    started, completed = Event(), Event()

    def second_writer():
        second = DatabaseWrapper(config)
        try:
            second.ensure_connection()
            started.set()
            second._start_transaction_under_autocommit()
            with second.cursor() as cursor:
                cursor.execute('SELECT value FROM counter')
                current = cursor.fetchone()[0]
                cursor.execute('UPDATE counter SET value = %s', [current + 1])
            second.commit()
            completed.set()
        finally:
            second.close()

    try:
        with first.cursor() as cursor:
            cursor.execute('CREATE TABLE counter (value INTEGER)')
            cursor.execute('INSERT INTO counter VALUES (0)')
        first._start_transaction_under_autocommit()
        with first.cursor() as cursor:
            cursor.execute('SELECT value FROM counter')
            assert cursor.fetchone()[0] == 0
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(second_writer)
            try:
                assert started.wait(2)
                assert not completed.wait(.1)
                with first.cursor() as cursor:
                    cursor.execute('UPDATE counter SET value = 1')
            finally:
                first.commit()
            future.result(timeout=3)
        with first.cursor() as cursor:
            cursor.execute('SELECT value FROM counter')
            assert cursor.fetchone()[0] == 2
    finally:
        first.close()
