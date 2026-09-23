import json
import pytest
from pipeline.fakes import fake_llm
from pipeline.script import validate, write_script

NICHE = {"channel_name": "頻道", "audience": "新手", "tone": "白話", "facts": []}

def test_fake_llm_script_is_valid():
    s = write_script("題目", NICHE, fake_llm)
    assert len(s["segments"]) == 3

def test_json_wrapped_in_prose_is_parsed():
    body = json.loads(fake_llm("JSON"))
    s = write_script("題目", NICHE, lambda p: "好的:\n```json\n" + json.dumps(body, ensure_ascii=False) + "\n```")
    assert s["title"] == body["title"]

def test_prompt_forbids_numbers_when_no_facts():
    seen = []
    write_script("題目", NICHE, lambda p: seen.append(p) or fake_llm("JSON"))
    assert "全文不要出現任何數字" in seen[0]

@pytest.mark.parametrize("bad", [
    {"title": "", "description": "", "segments": [{"text": "a"}] * 3},
    {"title": "x" * 101, "description": "", "segments": [{"text": "a"}] * 3},
    {"title": "a<b", "description": "", "segments": [{"text": "a"}] * 3},
    {"title": "t", "description": "", "segments": [{"text": "a"}] * 2},
    {"title": "t", "description": "", "segments": [{"text": "a"}, {"text": " "}, {"text": "c"}]},
])
def test_validate_rejects(bad):
    with pytest.raises(ValueError):
        validate(bad)
