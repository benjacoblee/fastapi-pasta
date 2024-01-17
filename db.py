import os
from sqlalchemy import (
    create_engine,
)
from sqlalchemy.orm import sessionmaker
from constants import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
