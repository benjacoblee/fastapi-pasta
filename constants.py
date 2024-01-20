import os
from pydantic import constr

ACCESS_TOKEN_EXP_MINUTES = os.getenv("ACCESS_TOKEN_EXP_MINUTES") or 30
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///test.db"
SECRET_KEY = os.getenv("SECRET_KEY") or ""
ALGORITHM = os.getenv("ALGORITHM") or "HS256"

# Desc
PASSWORD_REQUIREMENTS = """
- Needs to be 8 characters in length
- Needs to have an uppercase character
- Needs to have a lowercase character
- Needs to have a digit
"""

# File paths
VIDEOS_DIR = "videos"

# File options
WRITE_BINARY = "wb"
READ_BINARY = "rb"

# Regexes
GENERAL_STR_REGEX = r"^[a-zA-Z\s]+$"
DIFFICULTY_REGEX = r"^[\w\s]+$"
CHARACTERISTIC_STR = constr(pattern=GENERAL_STR_REGEX)

# Statuses
ROUTE_NOT_FOUND = "Route not found"
UNAUTHORIZED = "Unauthorized"
INTERNAL_SERVER_ERROR = "Internal server error"
SUCCESS = "Success"
