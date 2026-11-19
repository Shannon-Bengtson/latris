"""/api/model-types serves everything a picker shows; /families its groups."""

from fastapi.testclient import TestClient

from latris.server.app import create_app


def test_model_types_carry_picker_text_and_family(empty_project_root):
    c = TestClient(create_app(project_root=empty_project_root))
    types = {t["id"]: t for t in c.get("/api/model-types").json()}
    assert types["mcda"]["availability"] == "stable" and types["mcda"]["family"] == "decisions"
    assert types["sd"]["answers"].endswith("?") and len(types["sd"]["key_features"]) >= 2
    families = c.get("/api/model-types/families").json()
    assert [f["id"] for f in families] == ["causal", "risk", "decisions"]
    assert {t["family"] for t in types.values()} <= {f["id"] for f in families}
