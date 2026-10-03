from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

from app.settings import load_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(load_settings().database_url, pool_pre_ping=True)
