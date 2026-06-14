"""Шаблоны конфигов при создании АТС: БД (static realtime) и диск (bootstrap)."""

from sqlalchemy.orm import Session

from app.core.config import config
from app.models.ast_conf import AsteriskConf
from app.schemas.asterisk import AsteriskInstanceCreate
from app.utils.ast_config_ini import seed_config_from_ini


def get_test_extensions_conf(transport_type: str = "udp") -> str:
    """Возвращает тестовый extensions.conf с примерами диалплана."""
    return """[from-internal]
exten => 777,1,NoOp(Сервис 777 от ${CALLERID(num)})
exten => 777,n,Answer()
exten => 777,n,Dial(PJSIP/101,30)
exten => 777,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?int777_done)
exten => 777,n,VoiceMail(101@default)
exten => 777,n,Hangup()
exten => 777,n(int777_done),Hangup()

exten => _XXX,1,NoOp(Звонок ${CALLERID(num)} -> ${EXTEN})
exten => _XXX,n,Dial(PJSIP/${EXTEN},30)
exten => _XXX,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?vm_done)
exten => _XXX,n,VoiceMail(${EXTEN}@default)
exten => _XXX,n,Hangup()
exten => _XXX,n(vm_done),Hangup()

exten => *97,1,NoOp(Голосовая почта ${CALLERID(num)})
exten => *97,n,Answer()
exten => *97,n,Wait(1)
exten => *97,n,VoiceMailMain(${CALLERID(num)}@default)
exten => *97,n,Hangup()

exten => 8097,1,NoOp(Голосовая почта ${CALLERID(num)})
exten => 8097,n,Answer()
exten => 8097,n,Wait(1)
exten => 8097,n,VoiceMailMain(${CALLERID(num)}@default)
exten => 8097,n,Hangup()

exten => 8000,1,NoOp(Очередь test-support)
exten => 8000,n,Answer()
exten => 8000,n,Queue(test-support,t,,,300)
exten => 8000,n,Hangup()

[from-external]
exten => 777,1,NoOp(Входящий на 777 от ${CALLERID(all)})
exten => 777,n,Answer()
exten => 777,n,Dial(PJSIP/101,30)
exten => 777,n,GotoIf($["${DIALSTATUS}"="ANSWER"]?ext777_done)
exten => 777,n,VoiceMail(101@default)
exten => 777,n,Hangup()
exten => 777,n(ext777_done),Hangup()

exten => *97,1,NoOp(Голосовая почта ${CALLERID(num)})
exten => *97,n,Answer()
exten => *97,n,Wait(1)
exten => *97,n,VoiceMailMain(${CALLERID(num)}@default)
exten => *97,n,Hangup()

exten => 8097,1,NoOp(Голосовая почта ${CALLERID(num)})
exten => 8097,n,Answer()
exten => 8097,n,Wait(1)
exten => 8097,n,VoiceMailMain(${CALLERID(num)}@default)
exten => 8097,n,Hangup()
"""


def _get_empty_extensions_conf() -> str:
    """Возвращает пустой extensions.conf без тестовых диалпланов."""
    return """[from-internal]

[from-external]
"""


def get_test_queues_conf() -> str:
    """Возвращает тестовый queues.conf с примером очереди."""
    return """[general]
persistentmembers = yes

[test-support]
strategy = rrmemory
timeout = 20
retry = 5
musicclass = default
member => PJSIP/101
member => PJSIP/102
"""


def _get_empty_queues_conf() -> str:
    """Возвращает пустой queues.conf без тестовых очередей."""
    return """[general]
persistentmembers = yes
"""


def seed_test_dialplan(
    db_cdr: Session,
    instance_id: int,
    transport_type: str = "udp",
) -> dict[str, int]:
    """Записывает тестовый диалплан (from-internal, from-external) и очередь test-support в ast_config."""
    filenames = ("extensions.conf", "queues.conf")
    db_cdr.query(AsteriskConf).filter(
        AsteriskConf.instance_id == instance_id,
        AsteriskConf.filename.in_(filenames),
    ).delete(synchronize_session=False)

    templates = {
        "extensions.conf": get_test_extensions_conf(transport_type),
        "queues.conf": get_test_queues_conf(),
    }
    row_counts: dict[str, int] = {}
    for filename, content in templates.items():
        seed_config_from_ini(db_cdr, instance_id, filename, content)
        row_counts[filename] = (
            db_cdr.query(AsteriskConf)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == filename,
            )
            .count()
        )
    db_cdr.commit()
    return row_counts


def get_db_config_templates(
    instance: AsteriskInstanceCreate,
    transport_type: str,
) -> dict[str, str]:
    """Конфиги, которые сидируются в ast_config."""

    return {
        "extensions.conf": _get_empty_extensions_conf(),
        "voicemail.conf": """[general]
format = wav49|gsm|wav
serveremail = asterisk
attach = yes
skipms = 3000
maxsilence = 10
minmessage = 1
maxmessage = 300
sendvoicemail = yes
review = yes

[default]
""",
        "queues.conf": _get_empty_queues_conf(),
        "stasis.conf": """[general]
enabled=no
""",
        "cdr.conf": """[general]
enable=yes
unanswered=yes

[csv]
usegmtime=yes
loguniqueid=yes
loguserfield=yes
""",
        "cdr_adaptive_odbc.conf": f"""[mysql]
connection={config.ASTERISK_ODBC_ID}
table={config.MYSQL_CDR_TABLE}
""",
        "manager.conf": f"""[general]
enabled = yes
port = {instance.ami_port}
bindaddr = 0.0.0.0

[{config.MYSQL_ASTERISK_USER}]
secret = {config.MYSQL_ASTERISK_USER_PASSWORD}
read = system,call,config
write = system,call,config,command
""",
        "rtp.conf": f"""[general]
rtpstart={instance.rtp_port_start}
rtpend={instance.rtp_port_end}
strictrtp=no
icesupport=no
""",
        "http.conf": f"""[general]
enabled=yes
bindaddr=0.0.0.0
bindport={instance.http_port}
""",
    }


def get_disk_config_templates(
    instance: AsteriskInstanceCreate,
    transport_type: str,
) -> dict[str, str]:
    """Конфиги, которые остаются на диске (bootstrap / ODBC / sorcery)."""
    async_tcp = "async_operations=1" if transport_type == "tcp" else ""

    return {
        "pjsip.conf": f"""[global]
endpoint_identifier_order=username,ip,anonymous

[transport-{transport_type}]
type=transport
protocol={transport_type}
bind=0.0.0.0:{instance.sip_port}
{async_tcp}
local_net=172.18.0.0/16
external_media_address={config.PJSIP_EXTERNAL_ADDRESS}
external_signaling_address={config.PJSIP_EXTERNAL_ADDRESS}
""",
        "asterisk.conf": f"""[directories]
astetcdir => /etc/asterisk
astmoddir => /usr/lib/asterisk/modules
astvarlibdir => /var/lib/asterisk
astdbdir => /var/lib/asterisk
astkeydir => /var/lib/asterisk
astdatadir => /var/lib/asterisk
astagidir => /var/lib/asterisk/agi-bin
astspooldir => /var/spool/asterisk
astsoundsdir => /opt/asterisk-core-sounds
astrundir => /var/run/asterisk
astlogdir => /var/log/asterisk

[options]
verbose = 3
debug = 0
maxfiles = 100000
systemname = {instance.name}
""",
        "modules.conf": """[modules]
autoload = yes
preload => res_sorcery.so
preload => res_sorcery_config.so
preload => res_sorcery_realtime.so
preload => res_sorcery_memory.so
preload => res_odbc.so
preload => res_config_odbc.so
load => pbx_config.so
load => app_dial.so
load => app_voicemail.so
load => app_playback.so
load => app_queue.so
load => app_stack.so
load => res_musiconhold.so
load => res_pjsip.so
load => res_pjsip_endpoint_identifier_user.so
load => res_rtp_asterisk.so
load => bridge_simple.so
load => bridge_softmix.so
load => codec_ulaw.so
load => codec_alaw.so
load => format_wav.so
load => format_gsm.so
load => format_pcm.so
load => cdr_adaptive_odbc.so
""",
        "musiconhold.conf": """[general]
[default]
mode=files
directory=/var/lib/asterisk/moh
random=yes
""",
        "logger.conf": """[general]
dateformat=%F %T
[logfiles]
console => debug,verbose,notice,warning,error
messages => debug,verbose,notice,warning,error
""",
        "pjsip_users.conf": "; PJSIP users: генерируется из БД (services/pjsip_disk_sync.py)\n",
        "sorcery.conf": """[res_pjsip]
transport=config,pjsip.conf,criteria=type=transport
global=config,pjsip.conf,criteria=type=global
endpoint=realtime,ps_endpoints
auth=realtime,ps_auths
aor=realtime,ps_aors
contact=memory

[res_pjsip_endpoint_identifier_ip]
identify=realtime,ps_endpoint_id_ips

[res_pjsip_endpoint_identifier_user]
endpoint=realtime,ps_endpoints
""",
        "res_odbc.conf": f"""[{config.ASTERISK_ODBC_ID}]
enabled => yes
dsn => {config.DSN}
username => {config.MYSQL_ASTERISK_USER}
password => {config.MYSQL_ASTERISK_USER_PASSWORD}
pre-connect => yes
""",
        "drivers/odbc.ini": f"""[{config.DSN}]
Description = MySQL connection to Asterisk
Driver      = MySQL
Database    = {config.MYSQL_DATABASE_CDR}
Server      = {config.MYSQL_CONTAINER_NAME}
User        = {config.MYSQL_ASTERISK_USER}
Password    = {config.MYSQL_ASTERISK_USER_PASSWORD}
Port        = {config.MYSQL_PORT}
""",
        "drivers/odbcinst.ini": """[MySQL]
Description = ODBC for MySQL
Driver      = /usr/lib/x86_64-linux-gnu/odbc/libmaodbc.so
FileUsage   = 1
""",
    }
