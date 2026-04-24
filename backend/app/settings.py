from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "ai-mems"
    database_url: str = "sqlite:///./memes.db"
    storage_dir: str = "./storage"

    allow_generation: bool = True
    ai_provider: str = "local_text"  # local_text | openai_images (optional)
    openai_api_key: str | None = None


settings = Settings()
