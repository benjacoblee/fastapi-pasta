import os
from typing import Annotated, Union
from fastapi import Depends, FastAPI, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import (
    create_engine,
    String,
    ForeignKey,
    Date,
    Integer,
    Text,
    Boolean,
    JSON,
)
from sqlalchemy.orm import (
    sessionmaker,
    Session,
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from enum import Enum as PyEnum
from pydantic import BaseModel
from pydantic.functional_validators import AfterValidator
from datetime import datetime, timedelta
from jose import JWTError, jwt, ExpiredSignatureError
from passlib.context import CryptContext
from dotenv import load_dotenv
from validators import is_at_least_8_chars, has_uppercase, has_lowercase, has_one_digit

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


class StatusDetail(BaseModel):
    status_code: int
    detail: str

    def __init__(self, status_code: int, detail=""):
        self.status_code = status_code
        self.detail = detail


class User(BaseModel):
    id: int
    username: str


class UserHash(User):
    id: int
    hashed_password: str


class Base(DeclarativeBase):
    pass


class Characteristics(PyEnum):
    JUG = "jug"
    SLOPER = "sloper"
    CRIMP = "crimp"
    PINCH = "pinch"
    POCKET = "pocket"
    UNDERCLING = "undercling"
    DYNO = "dyno"
    STATIC = "static"
    DYNAMIC = "dynamic"
    SLAB = "slab"
    OVERHANG = "overhang"


class Route(BaseModel):
    gym_name: str
    date: datetime
    difficulty: str
    characteristics: list[Characteristics]
    attempts: int
    sent: bool
    notes: str


class UserItem(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(30))
    hashed_password: Mapped[str] = mapped_column(String(30))
    routes: Mapped[list["RouteItem"]] = relationship(back_populates="user")


class RouteItem(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["UserItem"] = relationship(back_populates="routes")
    gym_name: Mapped[str] = mapped_column(String(30))
    date: Mapped[datetime] = mapped_column(Date)
    difficulty: Mapped[str] = mapped_column(String(30))
    characteristics: Mapped[list[Characteristics]] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer)
    sent: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str] = mapped_column(Text)


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
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


def verify_password(plain_password, hashed_password):
    return password_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_context.hash(password)


def list_characteristics():
    return [v.value for v in list(Characteristics)]


async def get_user(username: str, db: Session):
    db_item = db.query(UserItem).filter(UserItem.username == username).first()
    if db_item:
        return UserHash(**db_item.__dict__)


async def auth_user(username: str, password: str, db: Session):
    user = await get_user(username, db)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False

    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = (
        datetime.utcnow() + expires_delta
        if expires_delta
        else datetime.utcnow() + timedelta(minutes=15)
    )
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
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except JWTError:
        raise credential_exception


async def get_current_active_user(current_user: UserHash = Depends(get_current_user)):
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


@app.get("/users/me/items", response_model=list[Route])
async def read_own_items(
    current_user: UserItem = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    db_items = db.query(RouteItem).filter(RouteItem.user_id == current_user.id).all()
    return db_items


@app.get("/users/{user_id}/items", response_model=list[Route])
async def read_user_items(user_id: int, db: Session = Depends(get_db)):
    db_items = db.query(RouteItem).filter(RouteItem.user_id == user_id).all()
    return db_items


@app.post("/register", response_model=Union[User, StatusDetail])
async def register_user(
    username: Annotated[str, Query(min_length=6)],
    password: Annotated[
        str,
        AfterValidator(is_at_least_8_chars),
        AfterValidator(has_uppercase),
        AfterValidator(has_lowercase),
        AfterValidator(has_one_digit),
        Query(
            min_length=8,
            description="""
- Needs to be 8 characters in length
- Needs to have an uppercase character
- Needs to have a lowercase character
- Needs to have a digit
""",
        ),
    ],
    db: Session = Depends(get_db),
):
    user = await get_user(username, db)
    if user:
        raise HTTPException(400, detail="Username already taken")
    hashed_password = get_password_hash(password)
    db_item = UserItem(username=username, hashed_password=hashed_password)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return StatusDetail(200, detail="User creation successful")


@app.post("/routes", response_model=StatusDetail)
async def create_route(
    route: Route,
    current_user: UserItem = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        route_dict = {
            key: value
            for key, value in route.__dict__.items()
            if key != "characteristics"
        }
        route_item = RouteItem(
            **route_dict,
            user_id=current_user.id,
            characteristics=list_characteristics()
        )
        db.add(route_item)
        db.commit()
        db.refresh(route_item)
        return StatusDetail(status.HTTP_200_OK, detail="Success")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:
        return StatusDetail(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.get("/routes/characteristics", response_model=list[Characteristics])
async def get_characteristics():
    return list_characteristics()
