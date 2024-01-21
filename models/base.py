from pydantic import BaseModel as PydanticBaseModel
from datetime import datetime
from fastapi import WebSocket


class BaseModel(PydanticBaseModel):
    class Config:
        arbitrary_types_allowed = True


class Token(BaseModel):
    access_token: str
    token_type: str


class StatusDetail(BaseModel):
    status_code: int
    detail: str


class User(BaseModel):
    id: int
    username: str


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
