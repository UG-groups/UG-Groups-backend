from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from decouple import config
from jose.exceptions import ExpiredSignatureError, JWTError
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.registration.router import router as registration_router
from app.groups.router import router as groups_router
from app.registration.models import User, UserDraft
from app.groups.models import Group
from app.miscellaneous.utils import get_media_root


DB_URL = config("DB_URL", cast=str)
DB_NAME = config("DB_NAME", cast=str)

ORIGIN = config("ORIGIN", cast=str)


MEDIA_ROOT = get_media_root()

beanie_models = [User, UserDraft, Group]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init beanie
    app.mongo_client = AsyncIOMotorClient(DB_URL)
    await init_beanie(database=app.mongo_client[DB_NAME], document_models=beanie_models)

    # Checks if directories for media files exist and if not create them
    dirs = ["profileImages", "groupImages", "postMultimedia"]
    for directory in dirs:
        if not os.path.isdir(os.path.join(MEDIA_ROOT, directory)):
            os.makedirs(os.path.join(MEDIA_ROOT, directory))

    yield

    app.mongo_client.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(registration_router)
app.include_router(groups_router)


@app.exception_handler(ExpiredSignatureError)
def expired_signature_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=jsonable_encoder({
            "detail": "[ExpiredSignatureError] El token de autenticación ha caducado. \
Por favor vuelve a iniciar sesión"
        })
    )

@app.exception_handler(JWTError)
def jwt_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=jsonable_encoder({
            "detail": "[JWTError] Algo salió mal mientras se decodificaba tu token de \
autenticación. Por favor vuelve a iniciar sesión"
        })
    )

@app.exception_handler(InvalidId)
def invalidid_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=jsonable_encoder({
            "detail": "[InvalidId]"
        })
    )
