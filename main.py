from contextlib import asynccontextmanager

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
from app.registration.models import User, UserDraft


DB_URL = config("DB_URL", cast=str)
DB_NAME = config("DB_NAME", cast=str)

ORIGIN = config("ORIGIN", cast=str)


beanie_models = [User, UserDraft]

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.mongo_client = AsyncIOMotorClient(DB_URL)
    await init_beanie(database=app.mongo_client["ug-groups"], document_models=beanie_models)
    yield
    app.mongodb_client.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(registration_router)


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
