import os
from django.core.wsgi import get_wsgi_application

# Load .env for local dev. On Render the real env vars are already set,
# and override=False ensures they are never overwritten by the .env file.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
# Static files are served by WhiteNoiseMiddleware (in MIDDLEWARE in settings.py).
# Media files (dish images) are served by Django's URL route in urls.py (DEBUG mode)
# or by the hosting platform's CDN/storage in production.
