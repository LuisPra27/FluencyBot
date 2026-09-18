import os
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("FLUENCY_EMAIL")
PASSWORD = os.getenv("FLUENCY_PASSWORD")
AI_API_KEY = os.getenv("AI_API_KEY")

if not EMAIL:
    raise ValueError("Falta FLUENCY_EMAIL en el archivo .env")

if not PASSWORD:
    raise ValueError("Falta FLUENCY_PASSWORD en el archivo .env")

if not AI_API_KEY:
    raise ValueError("Falta AI_API_KEY en el archivo .env")
