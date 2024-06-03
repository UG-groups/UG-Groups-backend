from fastapi import HTTPException, status

from .models import Group

async def fetch_group(groupId: str):
    if not (group := await Group.get(groupId)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grupo solicitado no existe"
        )

    return group
