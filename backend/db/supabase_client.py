"""
Supabase client singleton using the service_role key.
All routers import this instance. Never use the anon key in the backend.
"""
import os

from dotenv import load_dotenv
from supabase import create_client

# Load .env when running from backend directory
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError(
        "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment or backend/.env"
    )

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
