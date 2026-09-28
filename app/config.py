import os


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eve.db")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-webhook-secret")
    BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))
    # emails listed here become admins on signup (admins manage centres/tests)
    ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}


settings = Settings()
