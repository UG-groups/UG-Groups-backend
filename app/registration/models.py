from datetime import datetime, timedelta
import uuid

from beanie import Document, before_event, Replace
from pydantic import BaseModel, EmailStr, Field

from . import enums


# ********* BASE MODELS *********
# Here we define models which may be used as base for schema models and beanie models

class UserBase(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    profileImage: str | None = None
    bio: str = ""
    userType: enums.UserTypeEnum
    division: str # TODO make this field enum
    academicLevel: enums.AcademicLevelEnum | None = None
    degreeName: str | None = None # TODO make this field enum


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


class PwdResetToken(Document):
    value: str = Field(default_factory=lambda: str(uuid.uuid4()))
    expirationDate: datetime = datetime.utcnow() + timedelta(minutes=5)
    userEmail: EmailStr

    class Settings:
        name = "pwdResetTokens"
