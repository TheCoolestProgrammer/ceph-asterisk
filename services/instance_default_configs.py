"""Шаблоны конфигов при создании АТС: БД (static realtime) и диск (bootstrap)."""

from config import config
from schemas.asterisk import AsteriskInstanceCreate


def get_db_config_templates(
    instance: AsteriskInstanceCreate,
    transport_type: str,
) -> dict[str, str]:
    """Конфиги, которые сидируются в ast_config."""

    return {
        # "pjsip.conf": f"""[global]
        # endpoint_identifier_order=username,ip,anonymous
        #
        # [transport-{transport_type}]
        # type=transport
        # protocol={transport_type}
        # bind=0.0.0.0:{instance.sip_port}
        # {async_tcp}
        # [101]
        # type=endpoint
        # context=from-internal
        # disallow=all
        # allow=ulaw,alaw
        # auth=101-auth
        # aors=101-aor
        #
        # [101-auth]
        # type=auth
        # auth_type=userpass
        # password=strongpassword
        # username=101
        #
        # [101-aor]
        # type=aor
        # max_contacts=1
        # default_expiration=3600
        #
        # [200]
        # type=endpoint
        # context=from-external
        # disallow=all
        # allow=ulaw,alaw
        # auth=200-auth
        # aors=200-aor
        # direct_media=no
        #
        # [200-auth]
        # type=auth
        # auth_type=userpass
        # password=customerpass
        # username=200
        #
        # [200-aor]
        # type=aor
        # max_contacts=1
        # """,
        "extensions.conf": """[from-internal]
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
""",
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
101 => 4242,Test Operator 101
102 => 4242,Test Operator 102
""",
        "queues.conf": """[general]
persistentmembers = yes

[test-support]
strategy = rrmemory
timeout = 20
retry = 5
musicclass = default
member => PJSIP/101
member => PJSIP/102
""",
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
