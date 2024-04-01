from typing import Literal
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer
from pydantic.networks import HttpUrl
from beanie import Document, before_event, Replace


class GroupImage(BaseModel):
    url: HttpUrl
    publicId: str
class Group(Document):
    name: str
    description: str
    groupImage: GroupImage | None = None
    groupColor: str | None = None
    externalLink: HttpUrl | None = None
    accessibility: Literal["public", "private"] = "public"
    whoCanPublish: Literal["members", "onlyAdmins"] = "members"
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    @field_serializer('groupImage', when_used="always")
    def serialize_group_image(self, groupImage: GroupImage | None):
        return groupImage.url if groupImage else None

    @before_event(Replace)
    def update_updatedAt_field(self):
        self.updatedAt = datetime.utcnow()

    class Settings:
        name = "groups"
