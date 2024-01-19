from dotenv import load_dotenv

load_dotenv()

import os
from datetime import datetime
from typing import Annotated, Union
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
    Query,
    File,
    UploadFile,
    Form,
)
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import (
    Session,
)
from pydantic.functional_validators import AfterValidator
from datetime import timedelta
from db import engine, get_db
from auth import (
    get_current_active_user,
    auth_user,
    create_access_token,
    get_user,
    get_password_hash,
)
from models.base import Token, StatusDetail, User, Characteristic, Route
from models.db import Base, UserItem, RouteItem, CharacteristicItem, VideoItem
from validators import is_at_least_8_chars, has_uppercase, has_lowercase, has_one_digit
from constants import (
    PASSWORD_REQUIREMENTS,
    ACCESS_TOKEN_EXP_MINUTES,
    ROUTE_NOT_FOUND,
    INTERNAL_SERVER_ERROR,
    VIDEOS_DIR,
    WRITE_BINARY,
    UNAUTHORIZED,
    SUCCESS,
)
from utils.main import (
    iterfile,
    generate_file_name,
    to_characteristics_list,
    get_new_characteristics,
)


app = FastAPI()


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
async def get_root():
    return StatusDetail(status_code=200, detail="OK")


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
            description=PASSWORD_REQUIREMENTS,
        ),
    ],
    db: Session = Depends(get_db),
):
    # linter will sometimes complain that this is not awaitable, but it returns a coroutine object that must be awaited
    user = await get_user(username, db)
    if user:
        raise HTTPException(400, detail="Username already taken")
    hashed_password = get_password_hash(password)
    db_item = UserItem(username=username, hashed_password=hashed_password)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return StatusDetail(status_code=200, detail="User creation successful")


@app.post("/routes", response_model=StatusDetail)
async def create_route(
    gym_name: str = Form(""),
    date: datetime = Form(datetime.now()),
    difficulty: str = Form(""),
    characteristics: list[str] = Form(),
    attempts: int = Form(ge=0),
    sent: bool = Form(False),
    notes: str = Form(""),
    upload_file: UploadFile = File(...),
    current_user: UserItem = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        c_list = to_characteristics_list(characteristics)
        new_characteristics = get_new_characteristics(c_list, db)
        db.add_all(new_characteristics)
        db.commit()
        route_characteristics = (
            db.query(CharacteristicItem)
            .filter(CharacteristicItem.name.in_(c_list))
            .all()
        )
        route_item = RouteItem(
            user_id=current_user.id,
            gym_name=gym_name,
            date=date,
            difficulty=difficulty,
            characteristics=route_characteristics,
            attempts=attempts,
            sent=sent,
            notes=notes,
        )
        db.add(route_item)
        db.commit()
        db.refresh(route_item)
        route_id = route_item.id
        video_id = upload_route_video(route_id, upload_file, db)
        if not video_id:
            db.rollback()
            return StatusDetail(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=INTERNAL_SERVER_ERROR,
            )
        route_item.video_id = video_id
        db.commit()
        return StatusDetail(status_code=status.HTTP_200_OK, detail=SUCCESS)
    except HTTPException:
        db.rollback()
        return StatusDetail(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR,
        )
    except Exception as exc:
        db.rollback()
        return StatusDetail(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR,
        )


def upload_route_video(
    route_id: int,
    upload_file: UploadFile,
    db: Session = Depends(get_db),
):
    try:
        if not os.path.exists(VIDEOS_DIR):
            os.mkdir(VIDEOS_DIR)
        contents = upload_file.file.read()
        dir_path = os.getcwd() + f"/{VIDEOS_DIR}/"
        filename = (
            dir_path + generate_file_name(upload_file.filename)
            if upload_file.filename
            else dir_path + generate_file_name()
        )
        with open(filename, WRITE_BINARY) as f:
            f.write(contents)
        upload_file.file.close()
        video_item = VideoItem(filename=filename, route_id=route_id)
        db.add(video_item)
        db.commit()
        return video_item.id
    except Exception:
        db.rollback()


@app.get("/routes/{route_id}/video")
def stream_video(route_id: int, db: Session = Depends(get_db)):
    route_item = db.query(RouteItem).filter(RouteItem.id == route_id).first()
    if not route_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ROUTE_NOT_FOUND
        )
    video_item = db.query(VideoItem).filter(VideoItem.id == route_item.video_id).first()
    if not video_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ROUTE_NOT_FOUND
        )
    try:
        return StreamingResponse(iterfile(video_item.filename), media_type="video/mp4")
    except Exception as exc:
        print(exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR,
        )


@app.get("/routes", response_model=list[Route])
async def list_routes(db=Depends(get_db)):
    return db.query(RouteItem).all()


@app.delete("/routes/{route_id}")
async def delete_route_by_id(
    route_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    route = db.query(RouteItem).filter(RouteItem.id == route_id).first()
    if not route:
        return StatusDetail(
            status_code=status.HTTP_404_NOT_FOUND, detail=ROUTE_NOT_FOUND
        )
    user = db.query(UserItem).filter(UserItem.id == current_user.id).first()
    if user and route.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=UNAUTHORIZED)
    db.delete(route)
    db.commit()
    return StatusDetail(status_code=200, detail=f"Route {route_id} deleted")


@app.put("/routes/{route_id}", response_model=StatusDetail)
async def edit_route_by_id(
    route_id: int,
    gym_name: str = Form(""),
    date: datetime = Form(datetime.now()),
    difficulty: str = Form(""),
    characteristics: list[str] = Form(),
    attempts: int = Form(ge=0),
    sent: bool = Form(False),
    notes: str = Form(""),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    to_update = db.query(RouteItem).filter(RouteItem.id == route_id).first()
    if not to_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Bad request"
        )
    if to_update.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED
        )
    try:
        c_list = to_characteristics_list(characteristics)
        new_characteristics = get_new_characteristics(c_list, db)
        db.add_all(new_characteristics)
        db.commit()
        route_characteristics = (
            db.query(CharacteristicItem)
            .filter(CharacteristicItem.name.in_(c_list))
            .all()
        )
        route = Route(
            gym_name=gym_name,
            date=date,
            difficulty=difficulty,
            characteristics=[],
            attempts=attempts,
            sent=sent,
            notes=notes,
            video_id=to_update.video_id,
        )
        for attr_name, new_val in route.__dict__.items():
            if attr_name in to_update.__dict__:
                setattr(to_update, attr_name, new_val)
            elif attr_name == "characteristics":
                to_update.characteristics = route_characteristics
        db.commit()
        return StatusDetail(status_code=200, detail=SUCCESS)
    except:
        db.rollback()


@app.get("/routes/{characteristic}", response_model=list[Route])
async def get_routes_by_characteristic(
    characteristic: str, db: Session = Depends(get_db)
):
    return (
        db.query(RouteItem)
        .filter(
            RouteItem.characteristics.any(CharacteristicItem.name == characteristic)
        )
        .all()
    )


@app.post("/characteristics", response_model=StatusDetail)
async def create_characteristic(
    name: str,
    _: User = Depends(
        get_current_active_user
    ),  # we don't use the variable but user needs to be logged in to create a characteristic
    db: Session = Depends(get_db),
):
    exists = (
        db.query(CharacteristicItem).filter(CharacteristicItem.name == name).first()
    )
    if exists:
        return StatusDetail(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="Item already exists",
        )
    characteristic_item = CharacteristicItem(name=name.strip())
    db.add(characteristic_item)
    db.commit()
    db.refresh(characteristic_item)
    return StatusDetail(status_code=200, detail=SUCCESS)


@app.get("/characteristics", response_model=list[Characteristic])
async def get_characteristics(db=Depends(get_db)):
    return db.query(CharacteristicItem).all()
