"""マスタテーブル用の汎用 CRUD ルーター生成。

    router = crud_router(Resource, "/resources", "Resources")

で次のエンドポイントができる:
    GET    /resources?locationId=1&resourceGroupId=2&includeDeleted=false
    GET    /resources/{id}
    POST   /resources
    PATCH  /resources/{id}
    DELETE /resources/{id}      （DeleteFlag 列があれば論理削除）

列名（camelCase）と一致するクエリパラメータは、等価条件の絞り込みに使う。
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import false, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.routers.deps import current_user
from app.schemas.base import python_type, schemas_for, to_camel


# レコードを識別する主キーが一つであることを確認して取得する。
def _pk_column(model: type):
    pks = list(model.__table__.primary_key.columns)
    if len(pks) != 1:
        raise ValueError(f"{model.__name__} needs a single-column primary key for CRUD")
    return pks[0]


# 検索条件の文字列を、対応する列の型へ変換する。
def _parse(value: str, py: Any) -> Any:
    if py is bool:
        return value.lower() in ("1", "true", "yes")
    if py in (int, float):
        return py(value)
    return value


# モデルの項目名から、一覧・取得・追加・更新・削除のAPIを生成する。
def crud_router(model: type, prefix: str, tag: str, order_by: str | None = None) -> APIRouter:
    Read, Create, Update = schemas_for(model)
    pk = _pk_column(model)
    # APIのorderId等を、対応するDBの列へ結び付けて検索する。
    columns = {to_camel(attribute.key): attribute.columns[0] for attribute in inspect(model).column_attrs}
    has_delete_flag = "DeleteFlag" in model.__table__.columns
    router = APIRouter(prefix=prefix, tags=[tag])

    # 対象レコードが存在し、論理削除されていないことを確認する。
    def get_or_404(db: Session, obj_id: int):
        obj = db.get(model, obj_id)
        if obj is None or (has_delete_flag and obj.DeleteFlag):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
        return obj

    # 変更を保存し、DB制約違反の場合は保存を取り消して理由を返す。
    def commit(db: Session):
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, f"Constraint violation: {exc.orig}") from exc

    # モデルの項目名に一致する検索条件と削除状態で一覧を絞り込む。
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

    # 指定したIDのレコードを取得する。
    @router.get("/{obj_id}", response_model=Read)
    def get_item(obj_id: int, db: Session = Depends(get_db)):
        return get_or_404(db, obj_id)

    # 受け取った項目と登録者を使い、新しいレコードを保存する。
    @router.post("", response_model=Read, status_code=status.HTTP_201_CREATED)
    def create_item(body: Create, db: Session = Depends(get_db), user: str = Depends(current_user)):
        obj = model(**body.model_dump(exclude_unset=True), CreatedBy=user)
        db.add(obj)
        commit(db)
        db.refresh(obj)
        return obj

    # 送信された項目だけを更新し、更新者とともに保存する。
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

    # 対応モデルに合わせて論理削除またはレコード削除を行う。
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
