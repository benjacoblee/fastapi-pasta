from fastapi import HTTPException
from pydantic import BaseModel as PydanticBaseModel, validator
from datetime import datetime
from fastapi import WebSocket


class BaseModel(PydanticBaseModel):
    class Config:
        arbitrary_types_allowed = True


class AccessToken(BaseModel):
    access_token: str
    token_type: str


class Token(AccessToken):
    refresh_token: str


class StatusDetail(BaseModel):
    status_code: int
    detail: str


class User(BaseModel):
    id: int
    username: str


class NewUser(BaseModel):
    username: str
    password: str

    @validator("username")
    def is_at_least_6_chars(cls, v):
        if not len(v) >= 6:
            raise HTTPException(
                status_code=400, detail="Username must be at least 6 characters"
            )
        return v

    @validator("password")
    def is_at_least_8_chars(cls, v):
        if not len(v) >= 8:
            raise HTTPException(
                status_code=400, detail="Password must be at least 8 characters"
            )
        return v

    @validator("password")
    def has_uppercase(cls, v):
        if not any(c.isupper() for c in v):
            raise HTTPException(
                status_code=400,
                detail="Password must have at least one uppercase character",
            )
        return v

    @validator("password")
    def has_lowercase(cls, v):
        if not any(c.islower() for c in v):
            raise HTTPException(
                status_code=400,
                detail="Password must have at least one lowercase character",
            )
        return v

    @validator("password")
    def has_one_digit(cls, v):
        if not any(c.isdigit() for c in v):
            raise HTTPException(
                status_code=400, detail="Password must have at least one digit"
            )
        return v


class UserHash(User):
    id: int
    hashed_password: str


class Characteristic(BaseModel):
    name: str


class Route(BaseModel):
    gym_name: str
    date: datetime
    difficulty: str
    characteristics: list[Characteristic]
    attempts: int
    sent: bool
    notes: str
    video_id: int


class Job(BaseModel):
    user_id: int
    video_id: int
    route_id: int
    completed: bool


class ActiveConnection(BaseModel):
    user_id: int
    websocket: WebSocket

    async def send_text(self, text: str):
        await self.websocket.send_text(text)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[ActiveConnection] = []

    async def connect(
        self,
        active_connection: ActiveConnection,
    ):
        await active_connection.websocket.accept()
        self.active_connections.append(active_connection)

    def disconnect(self, active_connection: ActiveConnection):
        self.active_connections.remove(active_connection)
