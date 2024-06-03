from datetime import datetime

from pydantic import Field
from pydantic.networks import HttpUrl
from beanie import Document, before_event, Replace, Link

from . import enums
from ..registration.models import User


class Group(Document):
    name: str
    description: str
    groupImage: str | None = None
    groupColor: str | None = None
    externalLink: HttpUrl | None = None
    accessibility: enums.AccessibilityEnum
    whoCanPublish: enums.WhoCanPublishEnum
    admins: list[Link[User]]
    members: list[Link[User]] = []
    joinRequests: list[Link[User]] = []
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    @before_event(Replace)
    def update_updatedAt_field(self):
        self.updatedAt = datetime.utcnow()

    class Settings:
        name = "groups"
