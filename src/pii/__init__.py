"""German PII redaction for the hackathon loop. Settings come from .env (+ ENV_FILE overrides, e.g. local/.env)."""
import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))
if os.getenv("ENV_FILE"):
    load_dotenv(os.environ["ENV_FILE"], override=True)
