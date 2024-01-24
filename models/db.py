from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    Date,
    Integer,
    Text,
    Boolean,
    Table,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class UserItem(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(30))
    hashed_password: Mapped[str] = mapped_column(String(30))
    routes: Mapped[list["RouteItem"]] = relationship(back_populates="user")


route_characteristic_association = Table(
    "route_characteristic",
    Base.metadata,
    Column("route_id", Integer, ForeignKey("routes.id")),
    Column("characteristic_id", Integer, ForeignKey("characteristics.id")),
)


class RouteItem(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["UserItem"] = relationship(back_populates="routes")
    gym_name: Mapped[str] = mapped_column(String(30))
    date: Mapped[datetime] = mapped_column(Date)
    difficulty: Mapped[str] = mapped_column(String(30))
    characteristics = relationship(
        "CharacteristicItem", secondary=route_characteristic_association
    )
    attempts: Mapped[int] = mapped_column(Integer)
    sent: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str] = mapped_column(Text)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=True)


class VideoItem(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String())
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), nullable=True)


class CharacteristicItem(Base):
    __tablename__ = "characteristics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(30))
    routes = relationship(
        "RouteItem",
        secondary=route_characteristic_association,
        overlaps="characteristics",
    )


class JobItem(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    created_at: Mapped[str] = mapped_column(Date)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    completed: Mapped[bool] = mapped_column(Boolean)


class RevokedTokenItem(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String, unique=True)
    revoked_at: Mapped[str] = mapped_column(Date)
