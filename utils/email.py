import resend
import logging
from src.config import RESEND_API_KEY

logger = logging.getLogger(__name__)

# Configure Resend API Key if available
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
else:
    logger.warning("RESEND_API_KEY is not configured in environment variables.")

DEFAULT_FROM_EMAIL = "onboarding@resend.dev"
# Primary destination email for Resend delivery
DEFAULT_TO_EMAIL = "markusdaniel171@gmail.com"

def send_resend_email(to=None, subject="", html="", text=None, from_email=None):
    """
    Sends an email using the Resend Python SDK.
    Always routes to DEFAULT_TO_EMAIL (markusdaniel171@gmail.com) for Resend compliance.
    """
    if not resend.api_key:
        logger.error("Cannot send email: RESEND_API_KEY is not set.")
        return None

    sender = from_email or DEFAULT_FROM_EMAIL
    clean_recipients = [DEFAULT_TO_EMAIL]

    params = {
        "from": sender,
        "to": clean_recipients,
        "subject": subject,
        "html": html,
    }
    
    if text:
        params["text"] = text

    try:
        logger.info(f"Sending email via Resend to {clean_recipients} with subject: '{subject}'")
        response = resend.Emails.send(params)
        return response
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {e}")
        return None