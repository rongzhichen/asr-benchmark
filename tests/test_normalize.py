import json

from asr_benchmark.normalize import lexical, to_timeline
from tests.conftest import FIXTURES


def test_lexical_strips_space_and_punctuation_and_normalises():
    assert lexical("大家好，欢迎 来到。") == "大家好欢迎来到"
    assert lexical("é") == lexical("é")  # NFC
    assert lexical("...") == ""


def test_doubao_timeline_preserves_order_and_times():
    raw = json.loads((FIXTURES / "doubao_sample.json").read_text(encoding="utf-8"))
    tl = to_timeline("doubao", raw)
    assert tl["native_utterances"] is True
    assert [u["start_ms"] for u in tl["utterances"]] == [120, 2100]
    assert tl["utterances"][0]["words"][0]["text"] == "大家好"
    assert tl["provider_duration_ms"] == 4200


def test_whisper_words_assigned_by_lexical_offsets_not_time():
    raw = {"text": "hello world again", "duration": 2.0,
           "segments": [{"text": "hello world", "start": 0.0, "end": 1.0}, {"text": "again", "start": 1.0, "end": 2.0}],
           "words": [{"word": "hello", "start": 0.0, "end": 0.4}, {"word": "world", "start": 0.4, "end": 1.0},
                     {"word": "again", "start": 1.0, "end": 2.0}]}
    tl = to_timeline("whisper", raw)
    assert [len(u["words"]) for u in tl["utterances"]] == [2, 1]
    assert tl["utterances"][1]["words"][0]["start_ms"] == 1000.0
    assert tl["unassigned_words"] == []


def test_whisper_word_crossing_segment_boundary_is_flagged_not_guessed():
    raw = {"text": "ab cd", "segments": [{"text": "ab c", "start": 0, "end": 1}, {"text": "d", "start": 1, "end": 2}],
           "words": [{"word": "ab", "start": 0, "end": 0.5}, {"word": "cd", "start": 0.5, "end": 2}]}
    tl = to_timeline("whisper", raw)
    flagged = [w for u in tl["utterances"] for w in u["words"] if w["association_issues"]]
    assert flagged and flagged[0]["association_issues"] == ["word_crosses_segment_text_boundary"]


def test_soniox_flat_tokens_become_one_utterance_without_native_segmentation():
    raw = {"text": "你好世界", "tokens": [{"text": "你好", "start_ms": 0, "end_ms": 300}, {"text": "世界", "start_ms": 300, "end_ms": 700}]}
    tl = to_timeline("soniox", raw)
    assert tl["native_utterances"] is False
    assert len(tl["utterances"]) == 1 and tl["utterances"][0]["end_ms"] == 700


def test_deepgram_channel_vs_utterance_disagreement_is_noted():
    raw = {"metadata": {"duration": 1.0}, "results": {"channels": [{"alternatives": [{"transcript": "a b", "words": [
        {"word": "a", "start": 0, "end": 0.4}, {"word": "b", "start": 0.4, "end": 1}]}]}],
        "utterances": [{"transcript": "a", "start": 0, "end": 0.4, "words": [{"word": "a", "start": 0, "end": 0.4}]}]}}
    tl = to_timeline("deepgram", raw)
    assert any("disagree" in n for n in tl["notes"])
