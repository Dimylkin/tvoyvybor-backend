import os

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str
    jwt_secret: str
    cors_origins: tuple[str, ...]
    app_env: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        jwt_secret=os.environ["JWT_SECRET"],
        cors_origins=tuple(
            origin.strip()
            for origin in os.environ["CORS_ORIGINS"].split(",")
            if origin.strip()
        ),
        app_env=os.environ["APP_ENV"],
    )
