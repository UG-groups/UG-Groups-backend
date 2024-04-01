from typing import Literal
from datetime import datetime

from beanie import Document, before_event, Replace, Link
from pydantic import BaseModel, EmailStr, Field, field_serializer
from pydantic.networks import HttpUrl

from ..groups.models import Group


# ********* BASE MODELS *********
# Here we define models which may be used as base for schema models and beanie models

class ProfileImage(BaseModel):
    url: HttpUrl
    publicId: str
class UserBase(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    profileImage: ProfileImage | None = None
    bio: str | None = None
    userType: Literal["student", "administrative/teacher"]
    isOfficialUser: bool = False
    division: str
    academicLevel: Literal["highSchool", "bachelor", "master", "PhD"] | None = None
    degreeName: str | None = None
    administeringGroups: list[Link[Group]] = []
    joinedGroups: list[Link[Group]] = []

    @field_serializer('profileImage', when_used="always")
    def serialize_profile_image(self, profileImage: ProfileImage | None):
        return profileImage.url if profileImage else None


# ********* BEANIE MODELS *********

class User(Document, UserBase):
    password: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

    @before_event(Replace)
    def update_updatedAt_field(self):
        self.updatedAt = datetime.utcnow()


class VerifyEmail(BaseModel):
    value: EmailStr
    code: str | None = None
    codeIssuedAt: datetime | None = None
class UserDraft(Document, UserBase):
    password: str
    email: VerifyEmail
    draftedAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "draftUsers"
