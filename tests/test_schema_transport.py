import pytest
from pydantic import ValidationError
from backend.agents.schema_transport import wire_schema
from backend.agents.learning_path.agent import SCHEMA
from mock_data.machine_learning import fixture_records


def test_provider_schema_omits_unsupported_bounds_but_local_validation_remains_strict():
    import json
    transport = wire_schema(SCHEMA)
    serialized = json.dumps(transport.model_json_schema())
    assert "minLength" not in serialized and "minItems" not in serialized
    _, records = fixture_records()
    plan = next(r["output"] for kind,r in records if kind == "self_study")
    assert SCHEMA.model_validate(plan)
    plan["steps"][0]["explanation"] = "Too short"
    assert transport.model_validate(plan)
    with pytest.raises(ValidationError):
        SCHEMA.model_validate(plan)
