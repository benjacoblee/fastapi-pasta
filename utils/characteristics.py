from sqlalchemy.orm import Session
from models.base import Characteristic
from models.db import CharacteristicItem


def to_characteristics_list(characteristics: list[Characteristic]):
    return [c.name for c in characteristics]


def get_new_characteristics(characteristics: list[Characteristic], db: Session):
    characteristics_list = to_characteristics_list(characteristics)
    existing_characteristics = (
        db.query(CharacteristicItem)
        .filter(CharacteristicItem.name.in_(characteristics_list))
        .all()
    )
    existing_names = {c.name for c in existing_characteristics}
    return [
        CharacteristicItem(name=c)
        for c in characteristics_list
        if c not in existing_names
    ]
