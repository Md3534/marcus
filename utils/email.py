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
# Fallback email for free/testing tier of Resend
DEFAULT_TO_EMAIL = "markusdaniel171@gmail.com"

def send_resend_email(to, subject, html, text=None, from_email=None):
    """
    Sends an email using the Resend Python SDK.
    `to` can be a string (comma-separated or single email) or a list of emails.
    """
    if not resend.api_key:
        logger.error("Cannot send email: RESEND_API_KEY is not set.")
        return None

    # Parse recipients
    if isinstance(to, str):
        recipients = [email.strip() for email in to.split(",") if email.strip()]
    elif isinstance(to, list):
        recipients = to
    else:
        recipients = [DEFAULT_TO_EMAIL]

    sender = from_email or DEFAULT_FROM_EMAIL
    
    # Ensure clean, unique recipients list
    clean_recipients = list(set([r.strip() for r in recipients if r and isinstance(r, str) and r.strip()]))
    if not clean_recipients:
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
        logger.warning(f"Resend send failed for recipients {clean_recipients}: {e}. Retrying with fallback recipient {DEFAULT_TO_EMAIL}...")
        try:
            params["to"] = [DEFAULT_TO_EMAIL]
            response = resend.Emails.send(params)
            return response
        except Exception as fallback_err:
            logger.error(f"Failed to send email via Resend fallback: {fallback_err}")
            return None