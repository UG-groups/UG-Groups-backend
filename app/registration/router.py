from typing import Annotated
from datetime import datetime, timedelta
import random
import string
import textwrap
import os

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, Body
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import EmailStr
from decouple import config
from passlib.context import CryptContext
from jose import jwt

from . import schemas
from .models import User, UserDraft, PwdResetToken
from ..groups.models import Group
from ..miscellaneous.dependencies import get_current_user, validate_upload_file
from ..miscellaneous.utils import get_media_root
from ..email_utils.send_email import send_verification_code_email, send_password_reset_email


# ENVIRONMENT VARIABLES
SECRET_KEY = config("SECRET_KEY", cast=str)
ALGORITHM = config("ALGORITHM", cast=str)

EMAIL_HOST = config("EMAIL_HOST", cast=str)
EMAIL_PORT = config("EMAIL_PORT", cast=str)
EMAIL_USERNAME = config("EMAIL_USERNAME", cast=str)
EMAIL_PASSWORD = config("EMAIL_PASSWORD", cast=str)
EMAIL_FROM = config("EMAIL_FROM", cast=str)

H_SECRET_KEY = config("H_SECRET_KEY", cast=str)


# MODULE'S GLOBAL VARIABLES
MEDIA_ROOT = get_media_root()

AUTH_TOKEN_EXPIRATION_MINUTES = 60 * 24 * 2

VERIF_CODE_RESEND_T = 3 # Minutes between verif. code resends and code valid time

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=["registration"])


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
    now = datetime.utcnow()

    characters = string.ascii_letters + string.digits
    code = ''.join(random.choice(characters) for _ in range(6))

    # Updates verif code and issued time on corresponding user for the given email
    draft_user = await UserDraft.find_one(UserDraft.email.value == email)
    draft_user.email.code = code
    draft_user.email.codeIssuedAt = now
    await draft_user.replace()

    send_verification_code_email(email, code)

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
    if await User.find_one(User.email == form_data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"email": "Ya existe un usuario con el correo proporcionado"}
        )

    # Validates that given passwords are equal
    if form_data.password != form_data.passwordConfirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"passwordConfirm": "Las contraseñas no coinciden"}
        )
    # TODO: Validate password strongness


    # If no errors found in submitted data saves user as draft (in draftUsers collection).
    # When the user verifies them email, user will be moved to users collection

    # if already exists in draftUsers a user with the given email delete them
    if draft_user := await UserDraft.find_one(UserDraft.email.value == form_data.email):
        await draft_user.delete()

    # saves user as draft
    await UserDraft(
        **form_data.model_dump(exclude=[
            "email", "password", "passwordConfirm"
        ]),
        password = pwd_context.hash(form_data.password),
        email = {
            "value": form_data.email
        },
    ).insert()

    await save_and_send_verif_code(form_data.email)

    return JSONResponse(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
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
        307: {"description": "User is pending for verification"},
        401: {"description": "Username and password don't match"},
        404: {"description": "User not found"}
    }
)
async def signin(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # Searches a user which matches the given email (username)
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
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            content=jsonable_encoder({
                "redirectPath": "/verify-email/",
                "email": form_data.username
            })
        )

    # If not found any user with the given email returns 404 error response
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"noField": f"""
            No existe ningún usuario registrado con el correo <{form_data.username}>
        """.strip()}
    )


@router.post("/request-password-reset/")
async def request_password_reset(email: EmailStr = Body(embed=True)):
    # Verifies a user with the given email exists
    if not (user := await User.find_one(User.email == email)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún usuario con el correo electrónico <{email}>"
        )

    # Checks if a token for password reset exists for the user making the request.
    # If token exist check if it's still valid, if is raise a HTTPException, else delete
    # current token
    if current_token := await PwdResetToken.find_one(PwdResetToken.userEmail == user.email):
        if datetime.utcnow() < current_token.expirationDate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=textwrap.dedent("""
                    Recientemente has solicitado una restauración de tu contraseña, espera
                    el tiempo asignado entre solicitudes (5 minutos) y vuelve a intentarlo
                """).replace("\n", " ").strip()
            )

        else:
            await current_token.delete()

    # Generates and saves a new token for password reset
    pwd_reset_token = await PwdResetToken(userEmail=user.email).insert()

    # Send email with the link for password resetting with token embbeded
    send_password_reset_email(user.email, pwd_reset_token.value)

    return {"msg": "ok"}


@router.post("/reset-password/")
async def reset_password(token: str, newPassword: str = Body(embed=True)):
    if (
        not (pwd_rst_tkn := await PwdResetToken.find_one(PwdResetToken.value == token)) or
        datetime.utcnow() > pwd_rst_tkn.expirationDate
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=textwrap.dedent("""
                El token proporcionado para restaurar la contraseña es invalido o ya expiró
            """)
        )

    user = await User.find_one(User.email == pwd_rst_tkn.userEmail)
    user.password = pwd_context.hash(newPassword)
    await user.replace()

    await pwd_rst_tkn.delete()

    return {"msg": "Contraseña restaurada exitosamente"}


@router.get("/me/", response_model=schemas.ProfileResponse)
async def get_profile_data(user=Depends(get_current_user)):
    return user


@router.get("/groups-iam-admin/", response_model=schemas.GroupsResponse)
async def get_groups_iam_admin(user: Annotated[User, Depends(get_current_user)]):
    return {"groups": await Group.find(Group.admins.id == user.id).to_list()}


@router.get("/groups-iam-member/", response_model=schemas.GroupsResponse)
async def get_groups_iam_member(user: Annotated[User, Depends(get_current_user)]):
    # pylint: disable=E1101
    return {"groups": await Group.find(Group.members.id == user.id).to_list()}


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


@router.patch("/me/profile-image/")
async def update_profile_image(
    profile_image: Annotated[UploadFile, Depends(validate_upload_file)],
    user = Depends(get_current_user)
):
    try:
        # Before saving the new image delete previous (if any exists)
        if user.profileImage:
            os.remove(MEDIA_ROOT + user.profileImage[6:])

        # Saves new profile image in filesystem
        path = f"/profileImages/{str(user.id)}.{profile_image.filename.split('.')[-1]}"
        with open(MEDIA_ROOT + path, "wb") as new_file:
            new_file.write(await profile_image.read())

        profile_image = "/media" + path
        user.profileImage = profile_image
        await user.replace()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error inesperado mientras se actualizaba tu foto de perfil"
        ) from exc

    return {"profileImage": profile_image}
