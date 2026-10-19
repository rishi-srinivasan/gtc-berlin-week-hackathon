import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from distil_prep import JOB, to_row  # noqa: E402


def test_row_shape_and_json_answer():
    r = to_row("Hallo Anna", [{"text": "Anna", "label": "GIVENNAME"}])
    assert [m["role"] for m in r["messages"]] == ["user", "assistant"]
    assert json.loads(r["messages"][1]["content"]) == {"entities": [{"text": "Anna", "label": "GIVENNAME"}]}


def test_empty_answer_is_nonempty_content():
    assert to_row("Kein PII", [])["messages"][1]["content"] == '{"entities": []}'


def test_job_description_fields_are_allowed():
    assert set(JOB) <= {"task_description", "llm_as_a_judge_instructions",
                        "synthetic_data_generation_instructions", "trace_processing_instructions"}
