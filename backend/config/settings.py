import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env.local', override=False)

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('Run scripts/init_env.py to generate local application secrets.')
DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,backend').split(',')
CSRF_TRUSTED_ORIGINS = [s for s in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if s]
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.staticfiles', 'rest_framework', 'processing',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('sqlite:///'):
    # Explicit opt-in for local checks only; Compose always uses PostgreSQL.
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3', 'NAME': database_url[len('sqlite:///'):],
        # Serialize local writers before an atomic read can become a write. A deferred
        # lock upgrade can fail immediately even when SQLite's busy timeout is set.
        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
    }}
elif database_url.startswith(('postgres://', 'postgresql://')):
    db = urlparse(database_url)
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': db.path.lstrip('/'),
        'USER': unquote(db.username or ''), 'PASSWORD': unquote(db.password or ''),
        'HOST': db.hostname, 'PORT': db.port or 5432, 'CONN_MAX_AGE': 60,
        'OPTIONS': {'connect_timeout': 5},
    }}
else:
    raise ImproperlyConfigured('DATABASE_URL must explicitly select PostgreSQL or local SQLite.')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'UTC'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
}
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', '86400'))
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if os.environ.get('TRUST_PROXY_HEADERS', 'false').lower() == 'true':
    # Production exposes only Caddy; Nginx/backend remain on the Docker network.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r'^api/health/$']
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_BROKER_TRANSPORT_OPTIONS = {'socket_connect_timeout': 2, 'socket_timeout': 2, 'visibility_timeout': 7200}
CELERY_TASK_PUBLISH_RETRY = False
CELERY_TASK_SOFT_TIME_LIMIT = 3300
CELERY_TASK_TIME_LIMIT = 3600
CELERY_RESULT_EXPIRES = 3600
CACHE_URL = os.environ.get('CACHE_URL', 'redis://localhost:6379/2')
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': CACHE_URL,
                      'OPTIONS': {'socket_connect_timeout': 2, 'socket_timeout': 2}}}
CONNECTION_ENCRYPTION_KEY = os.environ.get('CONNECTION_ENCRYPTION_KEY', '')
CONNECTION_TTL_SECONDS = int(os.environ.get('CONNECTION_TTL_SECONDS', '3600'))
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
RULE_CACHE_TTL_SECONDS = int(os.environ.get('RULE_CACHE_TTL_SECONDS', '3600'))
TRANSFORM_REQUESTS_PER_SLICE = 25
OPENAI_RULE_TIMEOUT_SECONDS = 25
DATASET_ROOT = Path(os.environ.get('DATASET_ROOT', BASE_DIR.parent / '.runtime' / 'datasets'))
MAX_SOURCE_BYTES = int(os.environ.get('MAX_SOURCE_BYTES', str(1024 * 1024 * 1024)))
MAX_EXCEL_BYTES = int(os.environ.get('MAX_EXCEL_BYTES', str(100 * 1024 * 1024)))
MAX_EXCEL_EXPANDED_BYTES = int(os.environ.get('MAX_EXCEL_EXPANDED_BYTES', str(512 * 1024 * 1024)))
MAX_DATASET_COLUMNS = 256
MAX_CELL_CHARACTERS = 65536
PREVIEW_CELL_CHARACTERS = 4096
SPARK_MASTER = os.environ.get('SPARK_MASTER', 'local[2]')
SPARK_PARTITIONS = int(os.environ.get('SPARK_PARTITIONS', '4'))
JOB_WATCHDOG_ENABLED = True
JOB_POLL_SECONDS = 1
JOB_HEARTBEAT_SECONDS = 5
JOB_STALE_SECONDS = int(os.environ.get('JOB_STALE_SECONDS', '90'))
JOB_QUEUE_REPUBLISH_SECONDS = 300
JOB_MAX_RECOVERIES = 2
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    # Request bodies / AWS wire traffic must never be logged.
    'loggers': {'boto3': {'level': 'WARNING'}, 'botocore': {'level': 'WARNING'},
                'httpx': {'level': 'WARNING'}, 'httpcore': {'level': 'WARNING'},
                'py4j': {'level': 'WARNING'}},
}
