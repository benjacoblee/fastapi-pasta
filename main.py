import os
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, String
from sqlalchemy.orm import (
    sessionmaker,
    Session,
    DeclarativeBase,
    Mapped,
    mapped_column,
)
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY") or ""

if not SECRET_KEY:
    raise Exception("Secret key missing")

ALGORITHM = os.getenv("ALGORITHM") or "HS256"
ACCESS_TOKEN_EXP_MINUTES = os.getenv("ACCESS_TOKEN_EXP_MINUTES") or 30
DATABASE_URL = "sqlite:///test.db"


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str | None = None


class UserInDB(User):
    hashed_password: str


class Base(DeclarativeBase):
    pass


class DBItem(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(30))
    hashed_password: Mapped[str] = mapped_column(String(30))


class DBUsername:
    def __init__(self, username: str):
        self.username = username


class Item(BaseModel):
    id: int
    username: str
    hashed_password: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth_2_scheme = OAuth2PasswordBearer(tokenUrl="token")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()


def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)


def verify_pw(plain_pw, hashed_pw):
    return pwd_context.verify(plain_pw, hashed_pw)


def get_pw_hash(pw):
    return pwd_context.hash(pw)


async def get_user(username: str, db: Session):
    db_item = db.query(DBItem).filter(DBItem.username == username).first()
    if db_item:
        return Item(**db_item.__dict__)


async def auth_user(username: str, pw: str, db: Session):
    user = await get_user(username, db)
    if not user:
        return False
    if not verify_pw(pw, user.hashed_password):
        return False

    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth_2_scheme), db: Session = Depends(get_db)
):
    credential_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credential_exception
        user = await get_user(username, db)
        return user
    except JWTError:
        raise credential_exception


async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)):
    return current_user


@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = await auth_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=float(ACCESS_TOKEN_EXP_MINUTES))
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@app.get("/users/me/items")
async def read_own_items(current_user: User = Depends(get_current_active_user)):
    return [{"item_id": 1, "owner": current_user.username}]


@app.post("/register", response_model=User)
async def register_user(username: str, pw: str, db: Session = Depends(get_db)):
    user = await get_user(username, db)
    if user:
        raise HTTPException(400, detail="Username already taken")
    hashed_pw = get_pw_hash(pw)
    db_item = DBItem(username=username, hashed_password=hashed_pw)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return await get_user(username, db)


@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    usernames = [item[0] for item in db.query(DBItem.username).all()]
    return usernames
