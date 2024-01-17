from dotenv import load_dotenv

load_dotenv()

from typing import Annotated, Union
from fastapi import Depends, FastAPI, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
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
from models.db import Base, UserItem, RouteItem, CharacteristicItem
from validators import is_at_least_8_chars, has_uppercase, has_lowercase, has_one_digit
from constants import PASSWORD_REQUIREMENTS, ACCESS_TOKEN_EXP_MINUTES
from utils.characteristics import get_new_characteristics, to_characteristics_list


app = FastAPI()


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)


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
    route: Route,
    current_user: UserItem = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        # we convert Characteristic objects to an array of strings
        # route_characteristics_names has to be an array of strings for the filter to work
        # filter will not work with route.characteristics, which is Characteristic class
        # don't change the type of Characteristic, because it is needed in read_own_items
        new_characteristics = get_new_characteristics(route.characteristics, db)
        db.add_all(new_characteristics)
        db.commit()
        # re-query is needed because the characteristics might not exist before this point in time
        route_characteristics = (
            db.query(CharacteristicItem)
            .filter(
                CharacteristicItem.name.in_(
                    to_characteristics_list(route.characteristics)
                )
            )
            .all()
        )
        route_dict = {
            key: value
            for key, value in route.__dict__.items()
            if key != "characteristics"
        }
        route_item = RouteItem(
            **route_dict, user_id=current_user.id, characteristics=route_characteristics
        )
        db.add(route_item)
        db.commit()
        db.refresh(route_item)
        return StatusDetail(status_code=status.HTTP_200_OK, detail="Success")
    except HTTPException as http_exc:
        raise http_exc
    except Exception:
        return StatusDetail(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Route not found"
        )
    user = db.query(UserItem).filter(UserItem.id == current_user.id).first()
    unauthorized_detail = StatusDetail(
        status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized"
    )
    if not user:
        return unauthorized_detail
    if route.user_id != user.id:
        return unauthorized_detail
    db.delete(route)
    db.commit()
    return StatusDetail(status_code=200, detail=f"Route {route_id} deleted")


@app.put("/routes/{route_id}", response_model=StatusDetail)
async def edit_route_by_id(
    route: Route,
    route_id: int,
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    for attr_name, new_val in route.__dict__.items():
        if attr_name in to_update.__dict__:
            setattr(to_update, attr_name, new_val)
        elif attr_name == "characteristics":
            new_characteristics = get_new_characteristics(route.characteristics, db)
            db.add_all(new_characteristics)
            db.commit()
            route_characteristics = (
                db.query(CharacteristicItem)
                .filter(
                    CharacteristicItem.name.in_(
                        to_characteristics_list(route.characteristics)
                    )
                )
                .all()
            )
            to_update.characteristics = route_characteristics
    db.commit()
    return StatusDetail(status_code=200, detail="Success")


@app.get("/routes/{characteristic}/", response_model=list[Route])
async def get_routes_by_characteristic(
    characteristic: str, db: Session = Depends(get_db)
):
    db_items = (
        db.query(RouteItem)
        .filter(
            RouteItem.characteristics.any(CharacteristicItem.name == characteristic)
        )
        .all()
    )
    return db_items


@app.post("/characteristics", response_model=StatusDetail)
async def create_characteristic(
    name: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return StatusDetail(status_code=403, detail="Unauthorized")
    characteristic_item = CharacteristicItem(name=name)
    db.add(characteristic_item)
    db.commit()
    db.refresh(characteristic_item)
    return StatusDetail(status_code=200, detail="Success")


@app.get("/characteristics", response_model=list[Characteristic])
async def get_characteristics(db=Depends(get_db)):
    return db.query(CharacteristicItem).all()
