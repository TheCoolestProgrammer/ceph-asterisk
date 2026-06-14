from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db, get_cdr_db
from app.models.asterisk_instance import AsteriskInstance
from app.models.ast_conf import AsteriskConf
from app.services.dialplan_contexts import list_dialplan_contexts
from app.schemas.dialplan import (
    DialplanContextUpdate,
    DialplanResponse,
    DialplanRowResponse,
    DialplanUpdate,
)
from app.services.ast_config_history import save_file_version
from app.services.asterisk_reload import AsteriskReloadError, reload_asterisk_config


router = APIRouter(prefix="/instances/{instance_id}/dialplan")


@router.get("", response_model=DialplanResponse)
async def get_dialplan(
    instance_id: int,
    filename: str = "extensions.conf",
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Получить текущий диалплан для АТС.

    Возвращает все строки extensions.conf в формате ast_config
    (cat_metric, var_metric, category, var_name, var_val, commented).
    """
    # Проверка существования АТС
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Получить все строки диалплана, отсортированные по метрикам
    rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == filename,
        )
        .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
        .all()
    )

    return DialplanResponse(
        instance_id=instance_id,
        filename=filename,
        rows=[DialplanRowResponse.model_validate(row) for row in rows],
    )


@router.get("/contexts", response_model=list[str])
async def get_dialplan_contexts(
    instance_id: int,
    filename: str = "extensions.conf",
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Список контекстов диалплана (для редактора и поля context в PJSIP).

    Возвращает уникальные category из extensions.conf в ast_config.
    """
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    return list_dialplan_contexts(db_cdr, instance_id, filename)


@router.get("/{context}", response_model=DialplanResponse)
async def get_dialplan_context(
    instance_id: int,
    context: str,
    filename: str = "extensions.conf",
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Получить диалплан только выбранного контекста.

    Возвращает строки extensions.conf для одного category.
    """
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    rows = (
        db_cdr.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == filename,
            AsteriskConf.category == context,
        )
        .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Dialplan context '{context}' not found for filename '{filename}'",
        )

    return DialplanResponse(
        instance_id=instance_id,
        filename=filename,
        rows=[DialplanRowResponse.model_validate(row) for row in rows],
    )


@router.put("/{context}", response_model=dict)
async def update_dialplan_context(
    instance_id: int,
    context: str,
    dialplan_update: DialplanContextUpdate,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Обновить диалплан только для одного контекста.

    Сохраняет старое состояние, удаляет строки выбранного context и добавляет новые.
    """
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    filename = dialplan_update.filename
    author = dialplan_update.change_author or "api"
    description = (
        dialplan_update.description or f"Updated context {context} via visual editor"
    )

    try:
        history_entry = save_file_version(
            db_cdr,
            instance_id,
            filename,
            description,
            author,
            commit=False,
        )

        db_cdr.query(AsteriskConf).filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == filename,
            AsteriskConf.category == context,
        ).delete(synchronize_session=False)

        for row_data in dialplan_update.rows:
            conf_row = AsteriskConf(
                instance_id=instance_id,
                filename=filename,
                cat_metric=row_data.cat_metric,
                var_metric=row_data.var_metric,
                category=context,
                var_name=row_data.var_name,
                var_val=row_data.var_val,
                commented=row_data.commented,
            )
            db_cdr.add(conf_row)

        db_cdr.commit()

        reload_message = ""
        if dialplan_update.reload_asterisk:
            try:
                reload_asterisk_config(str(instance.name))
                reload_message = "; Asterisk reloaded"
            except AsteriskReloadError as e:
                reload_message = f"; Asterisk reload failed: {e.message}"

        return {
            "message": f"Dialplan context '{context}' updated successfully{reload_message}",
            "filename": filename,
            "context": context,
            "rows_added": len(dialplan_update.rows),
            "history_version": history_entry.version,
            "history_id": history_entry.id,
        }

    except Exception as e:
        db_cdr.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update dialplan context: {str(e)}"
        )


@router.put("", response_model=dict)
async def update_dialplan(
    instance_id: int,
    dialplan_update: DialplanUpdate,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """
    Обновить диалплан для АТС.

    1. Сохраняет текущее состояние в ast_config_history
    2. Удаляет старые строки из ast_config
    3. Добавляет новые строки
    4. Опционально перезагружает Asterisk
    """
    # Проверка существования АТС
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    filename = dialplan_update.filename
    author = dialplan_update.change_author or "api"
    description = dialplan_update.description or "Updated via visual editor"

    try:
        # 1. Сохраняем старое состояние в историю
        history_entry = save_file_version(
            db_cdr,
            instance_id,
            filename,
            description,
            author,
            commit=False,
        )

        # 2. Удаляем старые строки
        db_cdr.query(AsteriskConf).filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == filename,
        ).delete(synchronize_session=False)

        # 3. Добавляем новые строки
        for row_data in dialplan_update.rows:
            conf_row = AsteriskConf(
                instance_id=instance_id,
                filename=filename,
                cat_metric=row_data.cat_metric,
                var_metric=row_data.var_metric,
                category=row_data.category,
                var_name=row_data.var_name,
                var_val=row_data.var_val,
                commented=row_data.commented,
            )
            db_cdr.add(conf_row)

        db_cdr.commit()

        # 4. Перезагружаем Asterisk если нужно
        reload_message = ""
        if dialplan_update.reload_asterisk:
            try:
                reload_asterisk_config(str(instance.name))
                reload_message = "; Asterisk reloaded"
            except AsteriskReloadError as e:
                reload_message = f"; Asterisk reload failed: {e.message}"

        return {
            "message": f"Dialplan updated successfully{reload_message}",
            "filename": filename,
            "rows_added": len(dialplan_update.rows),
            "history_version": history_entry.version,
            "history_id": history_entry.id,
        }

    except Exception as e:
        db_cdr.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update dialplan: {str(e)}"
        )
