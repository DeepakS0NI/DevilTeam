import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# ============================================================
# 🔑 GEMINI API KEY yahan .env file se aati hai:
#     GEMINI_API_KEY=AIza....
# Key banane ke liye: https://aistudio.google.com/apikey
# Key ko kabhi code ya GitHub mein commit mat karna.
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Fast + sasta model default hai. Better reasoning chahiye to "gemini-3.8-flash" daalo.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# ============================================================
# 🗄️ SQL DATABASE — .env mein DATABASE_URL
#   Kuch na daalo  -> SQLite file (backend/careshift.db), koi install nahi chahiye
#   MS SQL Server  -> mssql+pyodbc://sa:PASSWORD@localhost:1433/careshift?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
#   PostgreSQL     -> postgresql+psycopg://user:pass@host:5432/careshift
#   MySQL          -> mysql+pymysql://user:pass@host:3306/careshift
# ============================================================
BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(BACKEND_DIR / 'careshift.db').as_posix()}"

# Frontend ka URL (CORS). Comma-separated. "*" = sab allowed (sirf dev ke liye).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
