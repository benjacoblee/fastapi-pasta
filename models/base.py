from pydantic import BaseModel
from datetime import datetime


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
