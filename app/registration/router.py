from typing import Annotated
from datetime import datetime, timedelta, timezone
import random
import string
import json
import textwrap

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import EmailStr
from decouple import config
from passlib.context import CryptContext
from jose import jwt
import cloudinary
import cloudinary.api
import cloudinary.uploader
import requests

from . import schemas
from .models import User, UserDraft
from ..miscellaneous.dependencies import get_current_user
from ..email_utils.send_email import send_email


SECRET_KEY = config("SECRET_KEY", cast=str)
ALGORITHM = config("ALGORITHM", cast=str)

EMAIL_HOST = config("EMAIL_HOST", cast=str)
EMAIL_PORT = config("EMAIL_PORT", cast=str)
EMAIL_USERNAME = config("EMAIL_USERNAME", cast=str)
EMAIL_PASSWORD = config("EMAIL_PASSWORD", cast=str)
EMAIL_FROM = config("EMAIL_FROM", cast=str)

H_SECRET_KEY = config("H_SECRET_KEY", cast=str)


AUTH_TOKEN_EXPIRATION_MINUTES = 60 * 24 * 2

VERIF_CODE_RESEND_T = 3 # Minutes between verif. code resends and code valid time


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=["registration"])

cloudinary.config(
  cloud_name = config("CLOUD_NAME", cast=str),
  api_key = config("API_KEY", cast=str),
  api_secret = config("API_SECRET", cast=str),
)


def generate_authentication_token(user_id):
    expires = datetime.utcnow() + timedelta(minutes=AUTH_TOKEN_EXPIRATION_MINUTES)
    encoded_jwt = jwt.encode(
        {"sub": str(user_id), "exp": expires},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {"accessToken": encoded_jwt, "tokenType": "bearer"}

# TODO: comment this function
async def save_and_send_verif_code(email: str):
    now = datetime.now(tz=timezone.utc)

    characters = string.ascii_letters + string.digits
    code = ''.join(random.choice(characters) for _ in range(6))

    # Updates verif code and issue time on corresponding user for the given email
    draft_user = await UserDraft.find_one(UserDraft.email.value == email)
    draft_user.email.code = code
    draft_user.email.codeIssuedAt = now
    await draft_user.replace()

    send_email(email, code)

    return now + timedelta(minutes=VERIF_CODE_RESEND_T)


@router.post(
    "/signup/",
    responses={
        409: {"description": "Already exists a user with the given email"},
        400: {"description": "Provided data is invalid or incorrect"}
    }
)
async def signup(form_data: schemas.UserCreate):
    # Verifies it doesn't already exist a user with the provided email
    if await User.find_one({"email": form_data.email}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"email": f"Ya existe un usuario con el correo <{form_data.email}>"}
        )

    # Validates that given passwords are equal
    if form_data.password != form_data.passwordConfirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"passwordConfirm": "Las contraseñas no coinciden"}
        )
    # TODO: Validate password strongness

    # Verifies hCaptcha token is valid
    h_response = requests.post(
        url="https://api.hcaptcha.com/siteverify",
        data={ 'secret': H_SECRET_KEY, 'response': form_data.captchaToken },
        timeout=1.5
    )
    h_response_json = json.loads(h_response.content)
    if not h_response_json['success']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"captchaToken": "Token hCaptcha invalido"}
        )


    # If no errors in submitted data saves user as draft (in draftUsers collection).
    # When the user verifies them email, user will be moved to users collection

    # if already exists in draftUsers a user with the given email delete them
    if draft_user := await UserDraft.find_one(UserDraft.email.value == form_data.email):
        await draft_user.delete()

    # saves user as draft
    await UserDraft(
        **form_data.model_dump(exclude=[
            "email", "password", "passwordConfirm", "captchaToken"
        ]),
        password = pwd_context.hash(form_data.password),
        email = {
            "value": form_data.email
        },
    ).insert()

    await save_and_send_verif_code(form_data.email)

    return JSONResponse(
        status_code=status.HTTP_300_MULTIPLE_CHOICES,
        content=jsonable_encoder({
            "redirectPath": "/verify-email/",
            "email": form_data.email
        })
    )


@router.post("/verify-email/", response_model=schemas.Token)
async def verify_email(
    email: EmailStr,
    body: schemas.Code
):
    if not (draft_user := await UserDraft.find_one(UserDraft.email.value == email)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún usuario con el correo <{email}>"
        )

    # Verify given verification code is valid
    if draft_user.email.code != body.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de verificación que proporcionaste no es valido"
        )
    if (
        datetime.utcnow() >
        draft_user.email.codeIssuedAt + timedelta(minutes=VERIF_CODE_RESEND_T)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de verificación que proporcionaste ya expiró"
        )

    # If verification code is valid moves user to users collection, and returns the auth token
    user = await User(
        **draft_user.model_dump(exclude=["id", "email", "draftedAt"]),
        email = draft_user.email.value,
    ).insert()
    await draft_user.delete()

    return generate_authentication_token(user.id)


@router.get(
    "/resend-verification-code/",
    responses={
        400: {"description": "it hasn't passed yet the interval time between code resends"},
        404: {"description": "user with given email not found"},
    }
)
async def resend_verification_code(
    email: str
) -> str:
    if not (draft_user := await UserDraft.find_one(UserDraft.email.value == email)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún usuario con el correo <{email}>"
        )

    # Verifies it has passed the minimum time betwee code resends and if so then generates,
    # saves and sends the new verification code
    if (
        datetime.utcnow() >
        draft_user.email.codeIssuedAt + timedelta(minutes=VERIF_CODE_RESEND_T)
    ):
        code_available_until = await save_and_send_verif_code(email)
        return code_available_until.isoformat()

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": textwrap.dedent("""
                    Recientemente se envió un código de verificación a este correo
                    electrónico, espera el tiempo asignado entre reenvios y vuelve
                    a intentar
                """).replace("\n", " ").strip(),
                "availableAt": (
                    draft_user.email.codeIssuedAt +
                    timedelta(minutes=VERIF_CODE_RESEND_T)
                ).isoformat() + "Z"
            }
        )


# For this path operation we are recovering sign in data as the documentation suggest, which is
# using OAuth2PasswordRequestForm. For this reason we spect to recieve user's email through the
# username field in the form data.
@router.post(
    "/signin/",
    response_model=schemas.Token,
    responses={
        300: {"description": "User is pending for verification"},
        401: {"description": "Username and password don't match"},
        404: {"description": "User not found"}
    }
)
async def signin(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # Searches the user that matches the given email (username)
    if user := await User.find_one(User.email == form_data.username):

        if not pwd_context.verify(form_data.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
                detail={"noField": "El correo y la contraseña no coinciden"}
            )

        return generate_authentication_token(user.id)

    # Searches if given email corresponds to user in draft
    if await UserDraft.find_one(UserDraft.email.value == form_data.username):
        return JSONResponse(
            status_code=status.HTTP_300_MULTIPLE_CHOICES,
            content=jsonable_encoder({
                "redirectPath": "/verify-email/",
                "email": form_data.username
            })
        )

    # If not found any user for the given email returns 404 error response
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"noField": textwrap.dedent(f"""
            No existe ningún usuario registrado con el correo<{form_data.username}>
        """).strip()}
    )


@router.get("/me/", response_model=schemas.ProfileResponse)
async def get_profile_data(
    user=Depends(get_current_user)
):
    return user


@router.patch("/me/", response_model=schemas.ProfileResponse)
async def profile_patch(
    profilePatch: schemas.ProfilePatch,
    user = Depends(get_current_user)
):
    for key, value in profilePatch.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    await user.replace()
    await user.sync()

    return user


@router.patch("/me/update-profile-image/")
async def update_profile_image(
    profileImage: UploadFile,
    user = Depends(get_current_user)
):
    try:
        # Before uploading the image to cloudinary delete the previous (if any exists)
        if "profileImage" in user:
            cloudinary.api.delete_resources([user.profileImage.publicId])

        # Upload image to cloudinary
        upload_result = cloudinary.uploader.upload(profileImage.file, folder="profileImages")
        cloudinary_asset = cloudinary.api.resource_by_asset_id(upload_result["asset_id"])
        user.profileImage = {
            "url": cloudinary_asset["secure_url"],
            "publicId": cloudinary_asset["public_id"]
        }
        await user.replace()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error inesperado mientras se actualizaba tu foto de perfil"
        ) from exc

    return {"profileImageUrl": cloudinary_asset["secure_url"]}
