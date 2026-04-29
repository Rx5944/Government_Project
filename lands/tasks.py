import logging
from celery import shared_task
from django.utils import timezone
from detection.gee_utils import run_analysis

logger = logging.getLogger(__name__)

@shared_task(name="lands.tasks.run_satellite_scan_task")
def run_satellite_scan_task(officer_id=None):
    """
    Background task to run the GEE satellite scan and ML detection.
    """
    logger.info("Starting background satellite scan task...")
    
    start_time = timezone.now()
    try:
        results = run_analysis()
        elapsed = (timezone.now() - start_time).seconds
        
        if results.get('status') == 'success':
            results['elapsed'] = elapsed
            results['message'] = f"Satellite Scan Complete. Found {results.get('encroached_count', 0)} encroachments."
            logger.info(f"Scan complete in {elapsed}s. {results.get('encroached_count', 0)} encroached.")
        else:
            logger.warning(f"Scan issue: {results.get('message')}")
            
        return results
    except Exception as e:
        logger.error(f"Error in satellite scan task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@shared_task(name="lands.tasks.scheduled_land_monitoring")
def scheduled_land_monitoring():
    logger.info("Starting scheduled land monitoring...")
    run_satellite_scan_task()
