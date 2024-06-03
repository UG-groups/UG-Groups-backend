from pydantic import BaseModel, model_serializer
from pydantic.networks import HttpUrl, EmailStr

from .models import Group
from ..miscellaneous.pydantic_types import StrObjectId, ISOSerWrappedDt


# ********* Request schemas *********

# patch /groups/{groupId}/
class GroupPatch(BaseModel):
    description: str | None = None
    groupColor: str | None = None
    externalLink: HttpUrl | None = None


# ********* Response schemas *********

# post /groups/
class GroupUser(BaseModel):
    id: StrObjectId
    firstName: str
    lastName: str
    email: EmailStr
    profileImage: str | None = None
class GroupResponse(Group):
    admins: list[GroupUser]
    members: list[GroupUser]
    createdAt: ISOSerWrappedDt
    updatedAt: ISOSerWrappedDt

    @model_serializer(mode="wrap")
    def custom_serializer(self, default_serializer):
        del self.joinRequests
        self.admins = self.admins[:3]
        self.members = self.members[:3]

        return default_serializer(self)


# get /{groupId}/admins/
# get /{groupId}/members/
class GroupUsersResponse(BaseModel):
    users: list[GroupUser]
