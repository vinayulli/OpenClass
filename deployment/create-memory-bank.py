"""Run with uv run --extra cloud python deployment/create-memory-bank.py after GCP auth."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="hackathon-506016")
    parser.add_argument("--region", default="us-central1")
    args = parser.parse_args()
    state = Path(__file__).parent / "memory-bank.local.json"
    if state.exists():
        previous = json.loads(state.read_text())
        if previous["project"] != args.project or previous["region"] != args.region:
            raise RuntimeError("Existing memory-bank state belongs to a different project/region")
        print("Existing recorded Memory Bank:", previous["name"])
        print("Verify its existence/configuration in GCP before using it; no duplicate created.")
        return
    import agentplatform
    client = agentplatform.Client(project=args.project, location=args.region)
    bank = client.memory_banks.create(config={"display_name": "OpenClass learner memories"}, managed_semantic_memory_config={
        "unstructured_memory_configs": [{"memory_topics": [{"custom_memory_topic": {"label": "learning_evidence", "description": "Only source-linked concept performance, educator-reviewed learning gaps, stated learning goals and learning-format preferences. Preserve dates and source references. Never infer ability, disability, personality or sensitive traits; exclude names, contact details, credentials, exam answer keys and raw graded answers. Assessment scores remain authoritative in PostgreSQL, not memory."}}], "enable_third_person_memories": True}],
        "ttl_config": {"memory_revision_default_ttl": "7776000s"},
        "disable_memory_revisions": False,
    })
    result = {"project": args.project, "region": args.region, "name": bank.name, "id": bank.name.rsplit("/", 1)[-1]}
    state.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Memory Bank:", result["name"])
    print("Set GEAP_MEMORY_BANK_ID="+result["id"])
    print("Set GEAP_MEMORY_ENABLED=true after verifying the bank and IAM permissions.")


if __name__ == "__main__":
    main()
