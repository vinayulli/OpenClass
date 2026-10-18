"""Keep provider grammar simple; application schemas retain all validation rules."""
from functools import lru_cache
import types
from typing import get_args, get_origin, Union
from pydantic import BaseModel, create_model


def wire_type(annotation):
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return wire_schema(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list:
        return list[wire_type(args[0])]
    if origin in {Union, types.UnionType}:
        return Union[tuple(wire_type(arg) for arg in args)]
    return annotation


@lru_cache(maxsize=None)
def wire_schema(schema):
    if schema is None:
        return None
    fields = {name: (wire_type(field.annotation), ... if field.is_required() else field.default) for name, field in schema.model_fields.items()}
    return create_model(schema.__name__+"Wire", **fields)
