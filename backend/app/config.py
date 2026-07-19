from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "public" mode must never serve private-corpus content (see docs/design.md §3.5)
    app_mode: str = "private"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/mise"


settings = Settings()
