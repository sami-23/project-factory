from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    github_token: str = ""
    github_username: str = ""
    run_hour: int = 9       # UTC hour to run daily
    run_minute: int = 0
    data_dir: str = "data"

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
