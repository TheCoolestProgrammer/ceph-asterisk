import logging

from database import SessionLocal
from models.asterisk_instance import AsteriskInstance
from services.asterisk_reload import AsteriskReloadError, reload_asterisk_config
from services.instance_compose import InstanceComposeError, sync_instance_compose

logger = logging.getLogger(__name__)


def apply_ami_port_runtime(instance_id: int) -> None:
    """Применяет compose и reload после смены AMI-порта (фоновая задача)."""
    db = SessionLocal()
    try:
        instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.id == instance_id)
            .first()
        )
        if instance is None:
            logger.error("apply_ami_port_runtime: instance %s not found", instance_id)
            return

        try:
            sync_instance_compose(instance)
        except InstanceComposeError as e:
            logger.warning(
                "compose sync after ami_port change (instance=%s): %s %s",
                instance_id,
                e.message,
                e.stderr,
            )

        try:
            reload_asterisk_config(instance.name)
        except AsteriskReloadError as e:
            logger.warning(
                "asterisk reload after ami_port change (instance=%s): %s %s",
                instance_id,
                e.message,
                e.stderr,
            )
    finally:
        db.close()
