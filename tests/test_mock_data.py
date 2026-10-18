from mock_data.validate import load, validate


def test_mock_contracts_and_real_twin_snapshots():
    records = validate()
    assert len(records) == 130


def test_examples_do_not_claim_live_model_results():
    manifest = load("manifest.json")
    assert manifest["synthetic"] is True
    assert manifest["counts"]["agent_cases"] == 5
    twins = {t["student_id"]: t for t in load("learning_twins.json")}
    assert twins["mock-student-02"]["mastery"] is None
    sparse = next(c for c in twins["mock-student-05"]["concepts"] if c["id"] == "functions")
    assert sparse["mastery"] == 100
    assert sparse["status"] == "insufficient evidence"
