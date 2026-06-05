from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, BaseCDR, engine_cdr
from routes import cdr, users, auth, queues, voicemail, dialplan
from routes.instances import instances, instancesCRUD
from routes.instances.configs import instance_configs
from routes import logs
from routes import audio_files
from config import config
from ldap_auth import LDAPAuth
from elastic import setup_elastic_pipeline
from config import config

Base.metadata.create_all(bind=engine)
BaseCDR.metadata.create_all(bind=engine_cdr)
# setup_elastic_pipeline()
app = FastAPI(title="Asterisk Manager")
if config.DEV_MODE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Disposition",
            "Content-Type",
            "Content-Length",
            "Accept-Ranges",
        ],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://{config.PJSIP_EXTERNAL_ADDRESS}:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Disposition",
            "Content-Type",
            "Content-Length",
            "Accept-Ranges",
        ],
    )

app.include_router(cdr.router)
app.include_router(users.router)
app.include_router(queues.router)
app.include_router(voicemail.router)
app.include_router(instancesCRUD.router)
app.include_router(instances.router)
app.include_router(instance_configs.router)
app.include_router(auth.router)
app.include_router(audio_files.router)
app.include_router(logs.router)
app.include_router(dialplan.router)


@app.get("/health_check")
def health_check():
    return {"status": "ok"}
