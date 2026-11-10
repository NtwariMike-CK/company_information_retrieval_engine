from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    environment: str = "development"          # set to "production" on Render
    database_url: str = "postgresql://rag_app:change_me_app@localhost:5432/company_rag"
    db_pool_max: int = 10
    jwt_secret: str = DEV_JWT
    jwt_expire_minutes: int = 480
    secrets_encryption_key: str = ""          # Fernet key for API keys at rest
    superadmin_email: str = "superadmin@example.com"
    superadmin_password: str = "ChangeMe123!"
    superadmin_name: str = "Platform SuperAdmin"
    storage_dir: str = "./storage"
    embedded_worker: bool = True              # run the job worker inside the API process
    embed_pause_seconds: float = 0            # pause after each embedding batch (free-tier rate limits: try 12)
    frontend_url: str = "http://localhost:3000"   # used for links in emails
    smtp_host: str = ""                           # leave empty to only queue emails (status "skipped")
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Company RAG <no-reply@example.com>"
    smtp_tls: bool = True
    register_limit_per_hour: int = 10             # applicant sign-ups allowed per IP per hour (raise only for testing)
    notify_email: str = ""                        # extra address that receives "new company request" emails
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
