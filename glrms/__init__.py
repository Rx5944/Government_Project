# Import celery app so shared_task decorators work.
# Wrapped in try/except so the web server can start even without celery installed.
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass  # Celery not installed — automation tasks will be unavailable
