"""
Celery Application Configuration for GLRMS.

To use Celery:
  1. Install Redis: https://github.com/microsoftarchive/redis/releases
  2. pip install celery redis django-celery-beat django-celery-results
  3. Run: celery -A glrms worker --loglevel=info
  4. Run: celery -A glrms beat   --loglevel=info
"""

import os

try:
    from celery import Celery

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'glrms.settings')

    app = Celery('glrms')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    app.autodiscover_tasks()

    @app.task(bind=True, ignore_result=True)
    def debug_task(self):
        print(f'Celery debug task — request: {self.request!r}')

except ImportError:
    # Celery is not installed. The web server still works normally.
    # Use 'python scheduler.py' for background scheduling without Redis.
    app = None
