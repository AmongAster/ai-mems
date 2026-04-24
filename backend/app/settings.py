from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "ai-mems"
    database_url: str = "sqlite:///./memes.db"
    storage_dir: str = "./storage"

    allow_generation: bool = True
    ai_provider: str = "local_text"  # local_text | openai_images (optional)
    openai_api_key: str | None = None

    # Simple shared-secret for Telegram bot -> backend ingest endpoint.
    # If set, requests must include header: X-Telegram-Token: <value>
    telegram_ingest_token: str | None = None

    # Telegram bot settings (optional, for future bot-driven flows).
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


settings = Settings()
