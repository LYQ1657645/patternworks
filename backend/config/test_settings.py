import os

os.environ['DJANGO_SECRET_KEY'] = 'test-only-not-for-deployment'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['DJANGO_DEBUG'] = 'true'
os.environ['CONNECTION_ENCRYPTION_KEY'] = 'bW1tbW1tbW1tbW1tbW1tbW1tbW1tbW1tbW1tbW1tbW0='

from .settings import *  # noqa: F403

ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
JOB_WATCHDOG_ENABLED = False  # Thread behavior is covered separately; tests use atomic SQLite transactions.
