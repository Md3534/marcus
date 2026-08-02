from dotenv import load_dotenv
import os
from pathlib import Path

# 1. Resolve .env file location
# This finds the .env in the backend directory regardless of where you run the project from.
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'

# 2. Load environment variables
load_dotenv(dotenv_path=env_path)

# 3. Environment Detection
# Default to 'development' if not set to avoid attribute errors
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# 5. Core Application Settings
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# 6. Third Party Integrations
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
# Load and parse ALLOWED_ORIGINS
raw_origins = os.getenv("ALLOWED_ORIGINS", "")
if raw_origins and raw_origins != "[]":
    ALLOWED_ORIGINS = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
else:
    # Default origins for local development
    ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"]

PROJECT_NAME = os.getenv("PROJECT_NAME", "myproject API")