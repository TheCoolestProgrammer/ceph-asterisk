import logging

from app.core.database import SessionLocal
from app.models.asterisk_instance import AsteriskInstance
from app.services.asterisk_reload import AsteriskReloadError, reload_asterisk_config
from app.services.instance_compose import InstanceComposeError, sync_instance_compose

logger = logging.getLogger(__name__)


def apply_instance_ports_runtime(instance_id: int) -> None:
    """Compose + reload после смены AMI, HTTP или RTP (фоновая задача)."""
    db = SessionLocal()
    try:
        instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.id == instance_id)
            .first()
        )
        if instance is None:
            logger.error(
                "apply_instance_ports_runtime: instance %s not found", instance_id
            )
            return

        try:
            sync_instance_compose(instance)
        except InstanceComposeError as e:
            logger.warning(
                "compose sync after port change (instance=%s): %s %s",
                instance_id,
                e.message,
                e.stderr,
            )

        try:
            reload_asterisk_config(instance.name)
        except AsteriskReloadError as e:
            logger.warning(
                "asterisk reload after port change (instance=%s): %s %s",
                instance_id,
                e.message,
                e.stderr,
            )
    finally:
        db.close()


# обратная совместимость
apply_ami_port_runtime = apply_instance_ports_runtime
