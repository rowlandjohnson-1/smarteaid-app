 
# app/core/config.py
import os
from dotenv import load_dotenv
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Points to the 'backend' directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent 
ENV_PATH = BASE_DIR / '.env'
load_dotenv(dotenv_path=ENV_PATH)

# --- Core Settings ---
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "SmartEducator AI Detector API")
DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
API_V1_PREFIX: str = "/api/v1"

# --- Database Settings ---
MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017") # Placeholder!
DB_NAME: str = os.getenv("DB_NAME", "aidetector_dev")

# --- Kinde Settings (Placeholders) ---
KINDE_DOMAIN: str = os.getenv("KINDE_DOMAIN", "")
KINDE_CLIENT_ID: str = os.getenv("KINDE_CLIENT_ID", "")
KINDE_CLIENT_SECRET: str = os.getenv("KINDE_CLIENT_SECRET", "") 
KINDE_CALLBACK_URL: str = os.getenv("KINDE_CALLBACK_URL", "http://localhost:8000/api/v1/auth/callback") 

# --- Stripe Settings (Placeholders) ---
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")