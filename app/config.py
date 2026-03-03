import os

from dotenv import load_dotenv

load_dotenv()

# MySQL
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3307"))
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "codef_err_log")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# Codef API
CODEF_BASE_URL = "https://codef.io"
CODEF_LOGIN_PAYLOAD = {
    "email": os.getenv("CODEF_LOGIN_EMAIL", ""),
    "password": os.getenv("CODEF_LOGIN_PASSWORD", ""),
    "iv": os.getenv("CODEF_LOGIN_IV", ""),
}

# Collector
COLLECT_INTERVAL_MINUTES = int(os.getenv("COLLECT_INTERVAL", "5"))

# Slack Webhook
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
