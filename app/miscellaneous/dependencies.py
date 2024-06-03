from typing import Annotated
from decouple import config

from fastapi import Depends, HTTPException, status, UploadFile
from fastapi.security import OAuth2PasswordBearer
from jose import jwt

from ..registration.models import User


DB_URL = config('DB_URL', cast=str)
DB_NAME = config('DB_NAME', cast=str)

SECRET_KEY = config('SECRET_KEY', cast=str)
ALGORITHM = config('ALGORITHM', cast=str)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/signin/")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id = payload.get("sub")
    if (
        user := await User.get(user_id)
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            detail="Token de acceso invalido"
        )

    return user


def validate_upload_file(uploadFile: UploadFile):
    # Validates uploaded file isn't larger than 5 MB
    if uploadFile.size / 1000**2 > 5:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo enviado pesa mas de 5 MB"
        )

    # Validates uploaded file is of type image (jpg, jpeg or png)
    if uploadFile.content_type.split("/")[1] not in ["jpg", "jpeg", "png"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Solo puedes subir archivos jpg, jpeg o png"
        )

    return uploadFile
