from fastapi import HTTPException, status

from .models import Group
from ..registration.models import User


def check_user_is_group_admin(user: User, group: Group, custom_response: str | None = None):
    if user.id not in [admin.ref.id for admin in group.admins]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Esta acción está reservada para los administradores del grupo"
                if not custom_response else custom_response
            )
        )
