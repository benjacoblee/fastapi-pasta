import os

PASSWORD_REQUIREMENTS = """
- Needs to be 8 characters in length
- Needs to have an uppercase character
- Needs to have a lowercase character
- Needs to have a digit
"""
ACCESS_TOKEN_EXP_MINUTES = os.getenv("ACCESS_TOKEN_EXP_MINUTES") or 30
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///test.db"
SECRET_KEY = os.getenv("SECRET_KEY") or ""
ALGORITHM = os.getenv("ALGORITHM") or "HS256"
