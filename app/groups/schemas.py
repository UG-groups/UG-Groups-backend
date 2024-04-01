from pydantic import BaseModel
from pydantic.networks import HttpUrl

from .models import Group


# ********* Request schemas *********

# patch /groups/{groupId}
class GroupPatch(BaseModel):
    description: str | None = None
    groupColor: str | None = None
    externalLink: HttpUrl | None = None


# ********* Response schemas *********

# post /groups/
class GroupResponse(Group):
    pass
