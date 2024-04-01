from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status, Depends, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic.networks import HttpUrl
from decouple import config
import cloudinary
import cloudinary.api
import cloudinary.uploader

from . import schemas
from .models import Group
from ..registration.models import User
from ..miscellaneous.dependencies import get_current_user


router = APIRouter(prefix="/groups", tags=["groups"])

cloudinary.config(
  cloud_name = config("CLOUD_NAME", cast=str),
  api_key = config("API_KEY", cast=str),
  api_secret = config("API_SECRET", cast=str),
)


# Here path parameters were defined one by one manually (instead of using a Pydantic model)
# because for this path operation we expect to receive a file (groupImage), so request body
# should be sent as form data, forcing us to define all the expected fields in request's
# body as Form() path parameters.
@router.post("/", response_model=schemas.GroupResponse)
async def create_group(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    groupImage: Annotated[UploadFile | None, Form()] = None,
    groupColor: Annotated[str | None, Form()] = None,
    externalLink: Annotated[HttpUrl | None, Form()] = None,
    accessibility: Annotated[Literal["public", "private"] | None, Form()] = None,
    whoCanPublish: Annotated[Literal["members", "onlyAdmins"] | None, Form()] = None,
    user = Depends(get_current_user)
):
    # If included a group image in request uploads group image to cloudinary
    if groupImage:
        try:
            upload_result = cloudinary.uploader.upload(groupImage.file, folder="groupImages")
            cloudinary_asset = cloudinary.api.resource_by_asset_id(upload_result["asset_id"])

        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ocurrió un error inesperado mientras se subía la foto del grupo"
            ) from exc

    # Creates in db a new group with submitted data
    new_group = Group(
        name = name,
        description = description,
        groupImage = {
            "url": cloudinary_asset["secure_url"],
            "publicId": cloudinary_asset["public_id"]
        } if groupImage else None,
        groupColor = groupColor,
        externalLink = externalLink,
    )
    if accessibility:
        new_group.accessibility = accessibility
    if whoCanPublish:
        new_group.whoCanPublish = whoCanPublish

    created_group = await new_group.insert()

    # Add newly created group to user's administering and joined groups
    user.administeringGroups.append(created_group)
    user.joinedGroups.append(created_group)
    await user.replace()

    return created_group


@router.get("/info/{groupId}/", response_model=schemas.GroupResponse)
async def get_group(groupId: str):
    if not (group := await Group.get(groupId)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grupo solicitado no existe"
        )

    return group


@router.patch("/{groupId}/", response_model=schemas.GroupResponse)
async def patch_group(
    groupId: str,
    groupPatch: schemas.GroupPatch,
    user = Depends(get_current_user)
):
    if not (group := await Group.get(groupId)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grupo solicitado no existe"
        )

    await user.fetch_link(User.administeringGroups)
    if group not in user.administeringGroups:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Solo los administradores pueden editar la información de un grupo"
        )

    for key, value in groupPatch.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    await group.replace()
    await group.sync()

    return group


@router.patch("/update-group-image/{groupId}/")
async def update_profile_image(
    groupId: str,
    groupImage: UploadFile,
    user = Depends(get_current_user)
):
    if not (group := await Group.get(groupId)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grupo solicitado no existe"
        )

    await user.fetch_link(User.administeringGroups)
    if group not in user.administeringGroups:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Solo los administradores pueden editar la imagen de un grupo"
        )

    try:
        # Before uploading the image to cloudinary delete the previous (if any exists)
        if group.groupImage:
            cloudinary.api.delete_resources([group.groupImage.publicId])

        # Upload image to cloudinary
        upload_result = cloudinary.uploader.upload(groupImage.file, folder="groupImages")
        cloudinary_asset = cloudinary.api.resource_by_asset_id(upload_result["asset_id"])
        group.groupImage = {
            "url": cloudinary_asset["secure_url"],
            "publicId": cloudinary_asset["public_id"]
        }
        await group.replace()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error inesperado mientras se actualizaba la imagen del grupo"
        ) from exc

    return {"groupImageUrl": cloudinary_asset["secure_url"]}


@router.delete("/{groupId}/")
async def delete_group(groupId: str, user = Depends(get_current_user)):
    if not (group := await Group.get(groupId)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grupo solicitado no existe"
        )

    await user.fetch_link(User.administeringGroups)
    if group not in user.administeringGroups:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Solo los administradores pueden eliminar un grupo"
        )

    await user.fetch_link(User.joinedGroups)
    await group.delete()

    user.administeringGroups.remove(group)
    user.joinedGroups.remove(group)
    await user.replace()

    return JSONResponse(jsonable_encoder({"message": "Grupo eliminado exitosamente"}))
