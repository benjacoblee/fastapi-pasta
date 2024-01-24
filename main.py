from dotenv import load_dotenv

load_dotenv()

import os
import asyncio
from datetime import datetime
from typing import Annotated, Union
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    File,
    UploadFile,
    Form,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import (
    Session,
)
from pydantic.functional_validators import AfterValidator
from datetime import timedelta
from jose import jwt, ExpiredSignatureError, JWTError
from db import engine, get_db
from auth import (
    get_current_active_user,
    auth_user,
    create_token,
    get_user,
    get_password_hash,
    get_current_user,
)
from models.base import (
    Token,
    AccessToken,
    StatusDetail,
    User,
    Characteristic,
    Route,
    Job,
    ConnectionManager,
    ActiveConnection,
)
from models.db import Base, UserItem, RouteItem, CharacteristicItem, VideoItem, JobItem
from validators import is_at_least_8_chars, has_uppercase, has_lowercase, has_one_digit
from constants import (
    PASSWORD_REQUIREMENTS,
    ACCESS_TOKEN_EXP_MINUTES,
    REFRESH_TOKEN_EXP_DAYS,
    ROUTE_NOT_FOUND,
    INTERNAL_SERVER_ERROR,
    VIDEOS_DIR,
    WRITE_BINARY,
    UNAUTHORIZED,
    SUCCESS,
    GENERAL_STR_REGEX,
    DIFFICULTY_REGEX,
    CHARACTERISTIC_STR,
    REFRESH_SECRET_KEY,
    ALGORITHM,
    REFRESH,
    ACCESS,
)
from utils.main import (
    iterfile,
    generate_file_name,
    to_characteristics_list,
    get_new_characteristics,
    generate_file_path,
)
from services.video import add_compress_task


app = FastAPI()
manager = ConnectionManager()
jobs: list[Job] = []


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
    refresh_token_expires = timedelta(days=float(REFRESH_TOKEN_EXP_DAYS))
    access_token = create_token(
        ACCESS, data={"sub": user.username}, expires_delta=access_token_expires
    )
    refresh_token = create_token(
        REFRESH, data={"sub": user.username}, expires_delta=refresh_token_expires
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/refresh", response_model=AccessToken)
async def refresh_access_token(refresh_token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(refresh_token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        username = payload["sub"]
        user = db.query(UserItem).filter(UserItem.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=float(ACCESS_TOKEN_EXP_MINUTES))
        access_token = create_token(
            ACCESS, data={"sub": username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


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
    background_tasks: BackgroundTasks,
    gym_name: str = Form(pattern=GENERAL_STR_REGEX),
    date: datetime = Form(datetime.now()),
    difficulty: str = Form(pattern=DIFFICULTY_REGEX),
    characteristics: list[CHARACTERISTIC_STR] = Form(),  # type: ignore
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
        video_id = upload_route_video(
            route_id, current_user.id, upload_file, background_tasks, jobs, db
        )
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
    user_id: int,
    upload_file: UploadFile,
    background_tasks: BackgroundTasks,
    jobs: list[Job],
    db: Session = Depends(get_db),
):
    try:
        if not os.path.exists(VIDEOS_DIR):
            os.mkdir(VIDEOS_DIR)
        contents = upload_file.file.read()
        # generate file path with UUID here to prevent file name collision
        file_path = generate_file_path(upload_file.filename or generate_file_name())
        with open(file_path, WRITE_BINARY) as f:
            f.write(contents)
        upload_file.file.close()
        # old file is deleted, new_file_path is output dest for compressed file
        # we return out of the function before compression is completed
        new_file_path = generate_file_path(upload_file.filename or generate_file_name())
        video_item = VideoItem(filename=new_file_path, route_id=route_id)
        db.add(video_item)
        db.commit()
        jobs.append(
            Job(
                user_id=user_id,
                video_id=video_item.id,
                route_id=route_id,
                completed=False,
            )
        )
        add_compress_task(file_path, new_file_path, background_tasks, jobs, db)
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
    gym_name: str = Form(pattern=GENERAL_STR_REGEX),
    date: datetime = Form(datetime.now()),
    difficulty: str = Form(pattern=DIFFICULTY_REGEX),
    characteristics: list[CHARACTERISTIC_STR] = Form(),  # type: ignore
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
    name: Annotated[str, Query(pattern=GENERAL_STR_REGEX)],
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
    characteristic_item = CharacteristicItem(name=name)
    db.add(characteristic_item)
    db.commit()
    db.refresh(characteristic_item)
    return StatusDetail(status_code=200, detail=SUCCESS)


@app.get("/characteristics", response_model=list[Characteristic])
async def get_characteristics(db=Depends(get_db)):
    return db.query(CharacteristicItem).all()


@app.websocket("/video-job-status/token/{token}")
async def ws_endpoint(token: str, websocket: WebSocket, db: Session = Depends(get_db)):
    user = await get_current_user(token, db)
    assert (
        user is not None
    )  # get_current_user will raise exceptions if the token is invalid or expired, in which case frontend needs to revalidate token
    user_id = user.id
    existing_connection = next(
        (conn for conn in manager.active_connections if conn.user_id == user_id), None
    )
    if existing_connection:
        manager.disconnect(existing_connection)
    active_connection = ActiveConnection(user_id=user_id, websocket=websocket)
    await manager.connect(active_connection)
    try:
        while True:
            for job in jobs:
                for connection in manager.active_connections:
                    if job.user_id == connection.user_id and job.completed:
                        await connection.send_text(
                            f"{job.video_id} finished processing"
                        )
                        job_item = JobItem(
                            created_at=datetime.now(),
                            user_id=user_id,
                            video_id=job.video_id,
                            route_id=job.route_id,
                            completed=True,
                        )
                        db.add(job_item)
                        db.commit()
                        jobs.remove(job)
                        print(jobs)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        manager.disconnect(active_connection)
    except asyncio.CancelledError:
        pass


@app.get("/users/{user_id}/jobs", response_model=list[Job])
async def get_user_job_history(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    return db.query(JobItem).filter(JobItem.user_id == current_user.id).all()
