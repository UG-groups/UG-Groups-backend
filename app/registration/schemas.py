from datetime import datetime

from pydantic import BaseModel
from pydantic.networks import HttpUrl

from .models import UserBase


# ********* Request schemas *********

# post /signup/
class UserCreate(UserBase):
    password: str
    passwordConfirm: str
    captchaToken: str

# post /verify-code/
class Code(BaseModel):
    code: str

# patch /me/
class ProfilePatch(BaseModel):
    bio: str | None = None
    division: str
    academicLevel: str | None = None
    degreeName: str | None = None


# ********* Response schemas *********

# post /signin/
# post /verify-email/
class Token(BaseModel):
    accessToken: str
    tokenType: str

# get /me/
class ProfileResponse(UserBase):
    profileImageUrl: HttpUrl
    createdAt: datetime
    updatedAt: datetime
