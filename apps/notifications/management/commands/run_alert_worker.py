import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.notifications.alerts import check_and_send_expiry_milestone_emails

logger = logging.getLogger('alert_worker')

class Command(BaseCommand):
    help = 'Runs a background worker that periodically scans product batches for expiry milestones.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting background expiry alert worker..."))
        
        # Get check interval from environment or default to 60 seconds
        import os
        interval = int(os.environ.get('ALERT_WORKER_INTERVAL', 60))
        self.stdout.write(self.style.WARNING(f"Worker will scan inventory every {interval} seconds."))

        while True:
            try:
                self.stdout.write(f"[{timezone.now()}] Initiating automated inventory scan...")
                
                # Check and send milestone notifications/emails
                milestones_sent = check_and_send_expiry_milestone_emails()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Scan complete. Sent {milestones_sent} milestone warnings."
                    )
                )
            except Exception as e:
                logger.error(f"Error in alert worker: {e}", exc_info=True)
                self.stdout.write(self.style.ERROR(f"Error during alert worker execution: {e}"))
            
            # Sleep until next check
            time.sleep(interval)
