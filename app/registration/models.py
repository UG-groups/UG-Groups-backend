from typing import Literal
from datetime import datetime

from beanie import Document, before_event, Replace
from pydantic import BaseModel, EmailStr, Field


# ********* BASE MODELS *********
# Here we define models which may be used as base for schema models and beanie models

class UserBase(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    bio: str | None = None
    userType: Literal["student", "administrative/teacher"]
    division: str
    academicLevel: str | None = None
    degreeName: str | None = None


# ********* BEANIE MODELS *********

class ProfileImage(BaseModel):
    url: str
    publicId: str
class User(Document, UserBase):
    profileImage: ProfileImage | None = None
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
