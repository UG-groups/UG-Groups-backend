from typing import Annotated
import textwrap
import os

from fastapi import APIRouter, HTTPException, status, Depends, Form, UploadFile, Body
from pydantic.networks import HttpUrl

from . import schemas, enums
from .models import Group
from .dependencies import fetch_group
from .utils import check_user_is_group_admin
from ..miscellaneous.utils import get_media_root
from ..registration.models import User
from ..miscellaneous.dependencies import get_current_user, validate_upload_file


MEDIA_ROOT = get_media_root()

router = APIRouter(prefix="/groups", tags=["groups"])


# Here path parameters were defined one by one manually (instead of using a Pydantic model)
# because for this path we expect to receive a file (groupImage), so request body should
# be sent as form data, forcing us to define all expected fields in request's body as
# Form() path parameters.
@router.post("/", response_model=schemas.GroupResponse)
async def create_group(
    user: Annotated[User, Depends(get_current_user)],
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    accessibility: Annotated[enums.AccessibilityEnum, Form()],
    whoCanPublish: Annotated[enums.WhoCanPublishEnum, Form()],
    groupImage: Annotated[UploadFile | None, UploadFile] = None,
    groupColor: Annotated[str | None, Form()] = None,
    externalLink: Annotated[HttpUrl | None, Form()] = None
):
    # Creates in db a new group with submitted data
    new_group = Group(
        name = name,
        description = description,
        accessibility = accessibility,
        whoCanPublish = whoCanPublish,
        groupColor = groupColor,
        externalLink = externalLink,
        admins = [user]
    )
    new_group = await new_group.insert()

    # If recieved groupImage in request validates and saves it in file system
    if groupImage:
        validate_upload_file(groupImage)

        path = f"/groupImages/{str(new_group.id)}.{groupImage.filename.split('.')[-1]}"
        with open(MEDIA_ROOT + path, "wb") as new_file:
            new_file.write(await groupImage.read())

        new_group.groupImage = "/media" + path
        await new_group.replace()

    return new_group


# Path operation for returning all information of a group
@router.get("/{groupId}/", response_model=schemas.GroupResponse)
async def get_group_info(group: Annotated[Group, Depends(fetch_group)]):
    await group.fetch_link(Group.admins)
    await group.fetch_link(Group.members)
    return group


@router.patch("/{groupId}/")
async def patch_group(
    groupPatch: schemas.GroupPatch,
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)]
):
    check_user_is_group_admin(user, group)

    for key, value in groupPatch.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    await group.replace()
    await group.sync()

    return {"msg": "ok"}


@router.patch("/{groupId}/group-image/")
async def update_profile_image(
    group: Annotated[Group, Depends(fetch_group)],
    group_image: Annotated[UploadFile, Depends(validate_upload_file)],
    user: Annotated[User, Depends(get_current_user)]
):
    check_user_is_group_admin(user, group)

    try:
        # Before saving the new image delete previous (if any exists)
        if group.groupImage:
            os.remove(MEDIA_ROOT + group.groupImage[6:])

        # Saves new group image in filesystem
        path = f"/groupImages/{str(group.id)}.{group_image.filename.split('.')[-1]}"
        with open(MEDIA_ROOT + path, "wb") as new_file:
            new_file.write(await group_image.read())

        group_image = "/media" + path
        group.groupImage = group_image
        await group.replace()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error inesperado mientras se actualizaba la imagen del grupo"
        ) from exc

    return {"groupImage": group_image}


@router.delete("/{groupId}/")
async def delete_group(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)]
):
    check_user_is_group_admin(user, group)

    # If group has an image deletes it
    if group.groupImage:
        os.remove(MEDIA_ROOT + group.groupImage[6:])

    await group.delete()

    return {"msg": "ok"}


@router.get("/{groupId}/admins/", response_model=schemas.GroupUsersResponse)
async def get_group_admins(
    group: Annotated[Group, Depends(fetch_group)],
):
    await group.fetch_link(Group.admins)
    return {"users": group.admins}


@router.get("/{groupId}/members/", response_model=schemas.GroupUsersResponse)
async def get_group_members(
    group: Annotated[Group, Depends(fetch_group)],
):
    await group.fetch_link(Group.members)
    return {"users": group.members}


@router.post("/{groupId}/join/")
async def join_group(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)]
):
    # Checks that user hasn't already joined this group neither is in the list of users
    # that have requested to join
    if (
        user.id in [user.ref.id for user in group.members] or
        user.id in [user.ref.id for user in group.admins] or
        user.id in [user.ref.id for user in group.joinRequests]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=textwrap.dedent("""
                Ya estas dentro de este grupo o en la lista de usuarios que han solicitado
                unirse
            """).replace("\n", " ").strip()
        )

    # If group accessibility is public just add user tu members list
    if group.accessibility == "public":
        group.members.append(user)
        await group.replace()
        return {"msg": "Te uniste al grupo exitosamente"}

    # If group accessibility is private then add user to list of users that have requested
    # to join
    group.joinRequests.append(user)
    await group.replace()
    return {"msg": "Solicitud enviada exitosamente"}


@router.get("/{groupId}/join-requests/", response_model=schemas.GroupUsersResponse)
async def get_group_join_requests(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)]
):
    check_user_is_group_admin(user, group)

    await group.fetch_link(Group.joinRequests)
    return {"users": group.joinRequests}


@router.post("/{groupId}/approve-join-request/")
async def approve_join_request(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)],
    userToApprove: Annotated[str, Body()]
):
    check_user_is_group_admin(user, group)

    try:
        i_user_to_appr = [str(user.ref.id) for user in group.joinRequests].index(userToApprove)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=textwrap.dedent("""
                No se encontró ningún usuario en la lista de solicitudes de unión al grupo
                que corresponda con el id proporcionado
            """).replace("\n", " ").strip()
        ) from exc

    user_approved = await User.get(group.joinRequests.pop(i_user_to_appr).ref.id)
    group.members.append(user_approved)
    await group.replace()

    return {"msg": "ok"}


@router.post("/{groupId}/make-admin/")
async def make_member_admin(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)],
    member_granted: Annotated[str, Body()]
):
    check_user_is_group_admin(user, group)

    try:
        i_member = [str(user.ref.id) for user in group.members].index(member_granted)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=textwrap.dedent("""
                No se encontró en la lista de miembros ningún usuario que corresponda con el
                id proporcionado
            """).replace("\n", " ").split()
        ) from exc

    member_granted = await User.get(group.members.pop(i_member).ref.id)
    group.admins.append(member_granted)
    await group.replace()

    return {"msg": "ok"}


@router.post("/{groupId}/left/")
async def left_group(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)]
):
    try:
        i_user = [user.ref.id for user in group.members].index(user.id)
        del group.members[i_user]

    except ValueError as exc:
        try:
            i_user = [user.ref.id for user in group.admins].index(user.id)

            # If user is admin of the group but they is the only admin raise error
            if len(group.admins) == 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=textwrap.dedent("""
                        Ningún grupo puede quedarse sin administradores, agrega a un nuevo
                        administrador e intanta de nuevo
                    """).replace("\n", " ").strip()
                ) from exc

            del group.admins[i_user]

        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Al parecer no estas dentro de este grupo, ninguna acción fue realizada"
            ) from exc

    await group.replace()

    return {"msg": "ok"}


# Path operation for removing members or admins from a group
@router.post("/{groupId}/remove-member/")
async def remove_member_from_group(
    group: Annotated[Group, Depends(fetch_group)],
    user: Annotated[User, Depends(get_current_user)],
    userToRemove: Annotated[str, Body()]
):
    check_user_is_group_admin(user, group)

    try:
        i_user = [str(user.ref.id) for user in group.members].index(userToRemove)
        del group.members[i_user]

    except ValueError as exc:
        try:
            i_user = [str(user.ref.id) for user in group.admins].index(userToRemove)
            del group.admins[i_user]

        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=textwrap.dedent("""
                    No se encontró ningún usuario entre los miembros o administradores del
                    grupo que corresponda con el id proporcionado
                """).replace("\n", " ").strip()
            ) from exc

    await group.replace()

    return {"msg": "ok"}
