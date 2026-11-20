"""The base every schema model shares: strict (unknown fields are refused), fields settable by name or
alias, and — for the API's response types — every field the server always sends marked required, so the
app's generated types don't make it handle ``undefined`` for values that are always there."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        protected_namespaces=(),
        json_schema_serialization_defaults_required=True,
    )
