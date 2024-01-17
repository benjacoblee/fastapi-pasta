import os
from sqlalchemy import (
    create_engine,
)
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///test.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
