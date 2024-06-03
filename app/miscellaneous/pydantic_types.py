# Pydantic custom types

from typing import Annotated
from datetime import datetime

from pydantic import BeforeValidator, WrapSerializer


# Represents an ObjectId field in the database.
# It will be represented as a string on the model so that it can be serialized to JSON
StrObjectId = Annotated[str, BeforeValidator(str)]


# Python datetime wrapped with a custom json serializer for appending a capital Z at the end of
# the string representation of the datetime. This wrapping proccess in necessary to comply with
# the ISO standard for timestamp strings
def datetime_serializer(dt: datetime, handler, info) -> str | datetime:
    # partial result is the result of calling model_dump on a datetime field (for this case)
    partial_result = handler(dt, info)
    if info.mode == "json":
        return partial_result + "Z"
    return partial_result
ISOSerWrappedDt = Annotated[str | datetime, WrapSerializer(datetime_serializer)]
