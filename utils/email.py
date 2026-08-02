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

    # Resend free tier restrictions:
    # 1. From must be onboarding@resend.dev
    # 2. To must be the account owner's email (DEFAULT_TO_EMAIL)
    sender = from_email or DEFAULT_FROM_EMAIL
    
    # In development/testing/sandbox, we override recipients to DEFAULT_TO_EMAIL if we are using onboarding@resend.dev
    if sender == DEFAULT_FROM_EMAIL:
        recipients = [DEFAULT_TO_EMAIL]

    params = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    
    if text:
        params["text"] = text

    try:
        logger.info(f"Sending email via Resend to {recipients} with subject: '{subject}'")
        response = resend.Emails.send(params)
        return response
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {e}")
        return None