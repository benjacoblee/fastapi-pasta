import os
import uuid
from sqlalchemy.orm import Session
from models.db import CharacteristicItem
from constants import READ_BINARY, VIDEOS_DIR


def iterfile(stream_file):
    with open(stream_file, mode=READ_BINARY) as file_like:
        yield from file_like


def generate_file_name(filename: str = "") -> str:
    return f"{uuid.uuid4()}-{filename}"


def generate_file_path(orig_name: str):
    new_file_name = generate_file_name(orig_name)
    return os.getcwd() + f"/{VIDEOS_DIR}/" + new_file_name


def to_characteristics_list(arr: list[str]) -> list[str]:
    return arr[0].split(",")


def get_new_characteristics(characteristics: list[str], db: Session):
    existing_characteristics = (
        db.query(CharacteristicItem)
        .filter(CharacteristicItem.name.in_(characteristics))
        .all()
    )
    existing_names = {c.name for c in existing_characteristics}
    return [
        CharacteristicItem(name=c) for c in characteristics if c not in existing_names
    ]
