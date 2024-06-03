from pydantic import BaseModel

from .models import UserBase
from . import enums as registration_enums
from ..groups import enums as groups_enums
from ..miscellaneous.pydantic_types import StrObjectId, ISOSerWrappedDt


# ********* Request schemas *********

# post /signup/
class UserCreate(UserBase):
    password: str
    passwordConfirm: str


# post /verify-code/
class Code(BaseModel):
    code: str


# patch /me/
class ProfilePatch(BaseModel):
    bio: str
    division: str # TODO make this field enum
    academicLevel: registration_enums.AcademicLevelEnum | None = None
    degreeName: str | None = None # TODO make this field enum


# ********* Response schemas *********

# post /signin/
# post /verify-email/
class Token(BaseModel):
    accessToken: str
    tokenType: str


# get /me/
class ProfileResponse(UserBase):
    createdAt: ISOSerWrappedDt
    updatedAt: ISOSerWrappedDt


# get /groups-iam-admin/
# get /groups-iam-member/
class ListGroup(BaseModel):
    id: StrObjectId
    name: str
    groupImage: str | None = None
    groupColor: str | None = None
    accessibility: groups_enums.AccessibilityEnum
class GroupsResponse(BaseModel):
    groups: list[ListGroup]
