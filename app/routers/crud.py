"""マスタテーブル用の汎用 CRUD ルーター生成。

    router = crud_router(Resource, "/resources", "Resources")

で次のエンドポイントができる:
    GET    /resources?siteId=1&resourceGroupId=2&includeDeleted=false
    GET    /resources/{id}
    POST   /resources
    PATCH  /resources/{id}
    DELETE /resources/{id}      （DeleteFlag 列があれば論理削除）

列名（camelCase）と一致するクエリパラメータは、等価条件の絞り込みに使う。
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import false, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.routers.deps import current_user
from app.schemas.base import python_type, schemas_for, to_camel


def _pk_column(model: type):
    pks = list(model.__table__.primary_key.columns)
    if len(pks) != 1:
        raise ValueError(f"{model.__name__} needs a single-column primary key for CRUD")
    return pks[0]


def _parse(value: str, py: Any) -> Any:
    if py is bool:
        return value.lower() in ("1", "true", "yes")
    if py in (int, float):
        return py(value)
    return value


def crud_router(model: type, prefix: str, tag: str, order_by: str | None = None) -> APIRouter:
    Read, Create, Update = schemas_for(model)
    pk = _pk_column(model)
    columns = {to_camel(c.key): c for c in model.__table__.columns}
    has_delete_flag = "DeleteFlag" in model.__table__.columns
    router = APIRouter(prefix=prefix, tags=[tag])

    def get_or_404(db: Session, obj_id: int):
        obj = db.get(model, obj_id)
        if obj is None or (has_delete_flag and obj.DeleteFlag):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
        return obj

    def commit(db: Session):
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, f"Constraint violation: {exc.orig}") from exc

    @router.get("", response_model=list[Read])
    def list_items(request: Request, db: Session = Depends(get_db)):
        stmt = select(model)
        params = request.query_params
        for key, value in params.items():
            col = columns.get(key)
            if col is not None:
                stmt = stmt.where(col == _parse(value, python_type(col.type)))
        if has_delete_flag and params.get("includeDeleted", "false").lower() != "true":
            stmt = stmt.where(model.DeleteFlag == false())
        sort_col = model.__table__.columns.get(order_by) if order_by else None
        stmt = stmt.order_by(sort_col if sort_col is not None else pk)
        return db.scalars(stmt).all()

    @router.get("/{obj_id}", response_model=Read)
    def get_item(obj_id: int, db: Session = Depends(get_db)):
        return get_or_404(db, obj_id)

    @router.post("", response_model=Read, status_code=status.HTTP_201_CREATED)
    def create_item(body: Create, db: Session = Depends(get_db), user: str = Depends(current_user)):
        obj = model(**body.model_dump(exclude_unset=True), CreatedBy=user)
        db.add(obj)
        commit(db)
        db.refresh(obj)
        return obj

    @router.patch("/{obj_id}", response_model=Read)
    def update_item(
        obj_id: int, body: Update, db: Session = Depends(get_db), user: str = Depends(current_user)
    ):
        obj = get_or_404(db, obj_id)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)
        obj.UpdatedBy = user
        commit(db)
        db.refresh(obj)
        return obj

    @router.delete("/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_item(obj_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
        obj = get_or_404(db, obj_id)
        if has_delete_flag:
            obj.DeleteFlag = True
            obj.UpdatedBy = user
        else:
            db.delete(obj)
        commit(db)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
