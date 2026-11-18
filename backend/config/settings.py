import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent      # backend/
PROJECT_ROOT = BASE_DIR.parent                           # repo root: backend/, frontend/, media/
FRONTEND_DIR = PROJECT_ROOT / 'frontend'                 # templates + static files

# Set these as environment variables in production (Render etc.).
# Local development: set DJANGO_DEBUG=1 (e.g. `set DJANGO_DEBUG=1` on Windows,
# `export DJANGO_DEBUG=1` on Mac/Linux). Debug is OFF unless you ask for it.
DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-change-me'
    else:
        raise ImproperlyConfigured('Set the DJANGO_SECRET_KEY environment variable.')

ALLOWED_HOSTS = [h for h in os.environ.get(
    'DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',') if h]
# Render sets this automatically, so the live site works without extra setup.
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
# e.g. DJANGO_CSRF_ORIGINS=https://yourapp.onrender.com
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('DJANGO_CSRF_ORIGINS', '').split(',') if o]
if RENDER_HOST:
    # Render always terminates HTTPS for us, even if someone later sets
    # DJANGO_DEBUG=1 on the live site to chase down an error (which flips
    # SECURE_PROXY_SSL_HEADER off below and would otherwise make Django
    # think every request is plain HTTP, then reject the HTTPS Origin
    # header on every POST with "CSRF token from POST incorrect"). Trusting
    # the Render host here does not depend on DEBUG, so this stays correct
    # either way.
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_HOST}')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'orders',
]
TIME_ZONE = 'Asia/Kolkata'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [FRONTEND_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [FRONTEND_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        # Compressed + hashed file names in production; plain storage in debug
        # so you don't need to run collectstatic while developing.
        'BACKEND': ('django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG
                    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'),
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Tokens never expire, so keep the browser session (which remembers the
# customer's orders) for 30 days.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

# ---------------------------------------------------------------------------
# Razorpay. Get the keys from Dashboard > Account & Settings > API Keys.
# Leave them unset in development: the site then uses a "test mode" pay button.
# ---------------------------------------------------------------------------
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')

# Dish photos uploaded in the admin
MEDIA_URL = '/media/'
MEDIA_ROOT = PROJECT_ROOT / 'media'
WHITENOISE_AUTOREFRESH = DEBUG   # re-scan files on every request only while developing

if RENDER_HOST:
    # Render terminates HTTPS in front of the app and always forwards this
    # header, on every deploy - not just when DEBUG is off. Tying this to
    # `not DEBUG` instead would mean turning DJANGO_DEBUG=1 on the live
    # Render site (e.g. to see a real traceback) makes Django think every
    # request is plain HTTP, which breaks the CSRF Origin check on every
    # POST ("CSRF token from POST incorrect") even though the browser is
    # really talking HTTPS the whole time.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
