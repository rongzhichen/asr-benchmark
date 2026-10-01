import json

from asr_benchmark.normalize import to_timeline
from asr_benchmark.validate import validate
from tests.conftest import FIXTURES


def _tl(utts):
    return {"text": "".join(u["text"] for u in utts), "utterances": utts, "unassigned_words": [], "native_utterances": True, "notes": []}


def _u(text, s, e, words):
    return {"text": text, "start_ms": s, "end_ms": e, "source_index": 0,
            "words": [{"text": t, "start_ms": ws, "end_ms": we, "confidence": None, "source_index": i, "association_issues": []}
                      for i, (t, ws, we) in enumerate(words)]}


def test_clean_timeline_is_fully_usable():
    v = validate(_tl([_u("ab", 0, 100, [("a", 0, 50), ("b", 50, 100)])]), 1000)
    assert v["issue_counts"] == {} and v["usable_word_fraction"] == 1.0 and v["usable_lexical_token_fraction"] == 1.0


def test_detects_each_structural_issue():
    v = validate(_tl([
        _u("ab", 0, 100, [("a", 0, 60), ("b", 50, 100)]),       # overlapping words
        _u("cdx", 90, 200, [("c", 90, 90), ("d", 180, 150), ("x", 190, 260)]),  # overlaps previous utterance; zero-duration; negative; outside utterance+audio
        _u("e", 300, 300, [("e", None, 300)]),                  # nonpositive utterance; missing word time
    ]), 250)
    c = v["issue_counts"]
    for key in ("word_overlap_or_nonmonotonic", "utterance_overlap_or_nonmonotonic", "zero_duration_word",
                "negative_duration_word", "word_outside_utterance", "nonpositive_utterance_duration",
                "missing_or_nonfinite_word_time", "utterance_outside_audio"):
        assert key in c, key
    assert v["usable_word_fraction"] < 1.0


def test_punctuation_tokens_are_formatting_not_lexical():
    raw = json.loads((FIXTURES / "doubao_sample.json").read_text(encoding="utf-8"))
    v = validate(to_timeline("doubao", raw), 4200)
    assert v["formatting_only_token_count"] == 3          # "，" "。" "。"
    assert v["lexical_token_count"] == 10
    assert v["issue_counts"].get("zero_duration_word") == 3  # only the punctuation entries
    assert v["usable_lexical_token_fraction"] == 1.0       # lexical tokens unaffected


def test_text_mismatch_between_levels_marks_everything_uncertain():
    tl = _tl([_u("ab", 0, 100, [("a", 0, 50), ("b", 50, 100)])])
    tl["text"] = "abc"
    v = validate(tl, 1000)
    assert v["full_text_utterance_lexical_agreement"] is False and v["usable_word_count"] == 0


def test_unknown_duration_skips_range_checks_only():
    v = validate(_tl([_u("a", 0, 100, [("a", 0, 100)])]), None)
    assert "utterance_outside_audio" not in v["issue_counts"] and v["usable_word_fraction"] == 1.0
