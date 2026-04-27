from dotenv import load_dotenv, find_dotenv
import os
from pathlib import Path

# Explicitly find and load the .env file in the backend directory
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# db
NEON_DB=os.getenv("NEON_DB")
DOCKER_DB=os.getenv("DOCKER_DB")
BACKEND_ON_DOCKER_DB=os.getenv("BACKEND_ON_DOCKER_DB", "postgresql://devuser:dev_password@db:5432/qstack_verify_db")
BACKEND_NOT_ON_DOCKER_DB=os.getenv("BACKEND_NOT_ON_DOCKER_DB", "postgresql://devuser:dev_password@localhost:5433/qstack_verify_db")


SECRET_KEY=os.getenv("SECRET_KEY", "change-this-secret-in-production")
ALGORITHM=os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
CLOUDINARY_CLOUD_NAME=os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY=os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET=os.getenv("CLOUDINARY_API_SECRET")
RESEND_API_KEY=os.getenv("RESEND_API_KEY")

MONNIFY_API_KEY=os.getenv("MONNIFY_API_KEY")
MONNIFY_SECRET_KEY=os.getenv("MONNIFY_SECRET_KEY")
MONNIFY_BUSINESS_CODE=os.getenv("MONNIFY_BUSINESS_CODE")
MONNIFY_BASE_URL=os.getenv("MONNIFY_BASE_URL")
MONNIFY_WALLET_ACCOUNT_NUMBER=os.getenv("MONNIFY_WALLET_ACCOUNT_NUMBER")
MONNIFY_CONTRACT_CODE=os.getenv("MONNIFY_CONTRACT_CODE")

# Verification logging (remove in production)
# print(f"DEBUG: MONNIFY_BASE_URL loaded as: {MONNIFY_BASE_URL}")