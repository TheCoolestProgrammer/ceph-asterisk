from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import docker

from database import Base, engine
from routes import cdr, users, auth
from routes.instances import instances, instancesCRUD
from routes.instances.configs import instance_configs

from config import config
from ldap_auth import LDAPAuth

Base.metadata.create_all(bind=engine)
# Docker client
docker_client = docker.from_env()
app = FastAPI(title="Asterisk Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ],  # Vue dev server порты
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cdr.router)
app.include_router(users.router)
app.include_router(instancesCRUD.router)
app.include_router(instances.router)
app.include_router(instance_configs.router)
app.include_router(auth.router)


@app.get("/health_check")
def health_check():
    return {"status": "ok"}
