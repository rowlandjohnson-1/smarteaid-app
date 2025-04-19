# app/core/config.py
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional # Added Optional

# --- Path Setup & .env Loading ---
# Assume .env is in the backend project root, two levels up from core
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / '.env'

# Check if .env exists and load it
try:
    if ENV_PATH.is_file():
        load_dotenv(dotenv_path=ENV_PATH)
        print(f"Loaded environment variables from: {ENV_PATH}") # Keep for debug
    else:
        print(f"Warning: .env file not found at {ENV_PATH}. Relying on system environment variables.")
except Exception as e:
    print(f"Error loading .env file from {ENV_PATH}: {e}")


# --- Logging Setup ---
# Configure logging level based on DEBUG setting
LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG", "False").lower() == "true" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Logger for this config module


# --- Core Settings ---
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "AI Detector API")
DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
VERSION: str = os.getenv("APP_VERSION", "0.1.0")
API_V1_PREFIX: str = "/api/v1"


# --- Database Settings ---
MONGODB_URL: Optional[str] = os.getenv("MONGO_CONNECTION_STRING") or os.getenv("MONGODB_URL")
DB_NAME: str = os.getenv("MONGO_DATABASE_NAME") or os.getenv("DB_NAME", "aidetector_dev")

if not MONGODB_URL:
    logger.warning("MONGODB_URL (or MONGO_CONNECTION_STRING) environment variable is not set.")
if not DB_NAME:
    logger.warning("DB_NAME (or MONGO_DATABASE_NAME) environment variable is not set.")


# --- Kinde Backend Settings ---
# Used for backend API token validation by security.py
KINDE_DOMAIN: Optional[str] = os.getenv("KINDE_DOMAIN")
KINDE_AUDIENCE: Optional[str] = os.getenv("KINDE_AUDIENCE")

if not KINDE_DOMAIN: logger.warning("KINDE_DOMAIN environment variable is not set.")
if not KINDE_AUDIENCE: logger.warning("KINDE_AUDIENCE environment variable is not set.")


# --- Azure Blob Storage Settings ---
# Used by services/blob_storage.py
AZURE_BLOB_CONNECTION_STRING: Optional[str] = os.getenv("AZURE_BLOB_CONNECTION_STRING")
AZURE_BLOB_CONTAINER_NAME: str = os.getenv("AZURE_BLOB_CONTAINER_NAME", "uploaded-documents") # Default if not set in .env

# Validate required Blob settings
if not AZURE_BLOB_CONNECTION_STRING:
    logger.warning("AZURE_BLOB_CONNECTION_STRING environment variable is not set. Blob storage operations will fail.")
if not AZURE_BLOB_CONTAINER_NAME:
     logger.warning("AZURE_BLOB_CONTAINER_NAME environment variable is not set. Using default 'uploaded-documents'.")


# --- Stripe Settings (Placeholders) ---
STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET")

# --- Add other environment variables below ---
# e.g., ML_API_URL, ML_API_KEY

# --- Log loaded settings (optional, careful with secrets in real logs) ---
# logger.debug(f"PROJECT_NAME: {PROJECT_NAME}")
# logger.debug(f"DEBUG: {DEBUG}")
# logger.debug(f"DB_NAME: {DB_NAME}")
# logger.debug(f"KINDE_DOMAIN: {KINDE_DOMAIN}")
# logger.debug(f"KINDE_AUDIENCE: {KINDE_AUDIENCE}")
# logger.debug(f"AZURE_BLOB_CONTAINER_NAME: {AZURE_BLOB_CONTAINER_NAME}")
# logger.debug(f"MONGODB_URL Set: {'Yes' if MONGODB_URL else 'No'}")
# logger.debug(f"AZURE_BLOB_CONNECTION_STRING Set: {'Yes' if AZURE_BLOB_CONNECTION_STRING else 'No'}")

