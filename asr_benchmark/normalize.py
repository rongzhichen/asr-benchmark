"""Convert each provider's raw payload into one common timeline schema.

Timeline = {
  "text": str,                       # provider's full transcript
  "provider_duration_ms": float|None,
  "utterances": [ {text, start_ms, end_ms, source_index, words: [ {text, start_ms, end_ms, confidence, source_index, association_issues} ]} ],
  "unassigned_words": [...],         # words the provider returned but that cannot be placed in an utterance
  "native_utterances": bool,         # False when the provider returned only a flat token stream
  "notes": [str]
}
Nothing is repaired or guessed: missing times stay None, provider order is preserved.
"""
from __future__ import annotations

import unicodedata
from typing import Any


def lexical(text: str) -> str:
    """Characters that carry meaning: NFC-normalised, no whitespace, no punctuation."""
    return "".join(c for c in unicodedata.normalize("NFC", text or "")
                   if not c.isspace() and not unicodedata.category(c).startswith("P"))


def _ms(value: Any, unit: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) * (1000 if unit == "seconds" else 1)


def _word(text, start, end, idx, confidence=None, issues=None):
    return {"text": text or "", "start_ms": start, "end_ms": end, "confidence": confidence,
            "source_index": idx, "association_issues": list(issues or [])}


def doubao(raw: dict) -> dict:
    result = raw.get("result", {})
    return {"text": result.get("text", ""), "provider_duration_ms": raw.get("audio_info", {}).get("duration"),
            "unassigned_words": [], "native_utterances": True, "notes": [],
            "utterances": [{"text": u.get("text", ""), "start_ms": u.get("start_time"), "end_ms": u.get("end_time"),
                            "source_index": i,
                            "words": [_word(w.get("text"), w.get("start_time"), w.get("end_time"), j, w.get("confidence"))
                                      for j, w in enumerate(u.get("words", []))]}
                           for i, u in enumerate(result.get("utterances", []))]}


def whisper(raw: dict) -> dict:
    """OpenAI verbose_json: segments and a flat word list. Words are assigned to segments by exact
    lexical offsets, never by timestamps or fuzzy matching; a word that spans two segments is flagged."""
    words, segments = raw.get("words", []), raw.get("segments", [])
    utterances = [{"text": s.get("text", ""), "start_ms": _ms(s.get("start"), "seconds"), "end_ms": _ms(s.get("end"), "seconds"),
                   "words": [], "source_index": i} for i, s in enumerate(segments)]
    ranges, offset = [], 0
    for s in segments:
        n = len(lexical(s.get("text", "")))
        ranges.append((offset, offset + n))
        offset += n
    full_match = (lexical(raw.get("text", "")) == lexical("".join(s.get("text", "") for s in segments))
                  == lexical("".join(w.get("word", "") for w in words)))
    offset, unassigned = 0, []
    for i, w in enumerate(words):
        n = len(lexical(w.get("word", "")))
        lower, upper = offset, offset + n
        offset = upper
        record = _word(w.get("word"), _ms(w.get("start"), "seconds"), _ms(w.get("end"), "seconds"), i)
        matches = [j for j, (a, b) in enumerate(ranges) if lower < b and upper > a] if full_match else []
        if matches:
            if len(matches) != 1:
                record["association_issues"].append("word_crosses_segment_text_boundary")
            utterances[matches[0]]["words"].append(record)
        else:
            record["association_issues"].append("unresolved_word_to_utterance")
            unassigned.append(record)
    return {"text": raw.get("text", ""), "utterances": utterances, "unassigned_words": unassigned,
            "provider_duration_ms": _ms(raw.get("duration"), "seconds"), "native_utterances": True,
            "notes": ["words assigned to segments by exact ordered lexical offsets; no guessed timestamps",
                      f"global word stream agrees with segments: {full_match}"]}


def microsoft(raw: dict) -> dict:
    phrases = raw.get("phrases", [])
    text = "\n".join(p.get("text", "") for p in raw.get("combinedPhrases", [])) or " ".join(p.get("text", "") for p in phrases)
    utts = []
    for i, p in enumerate(phrases):
        start = p.get("offsetMilliseconds")
        end = start + p["durationMilliseconds"] if start is not None and p.get("durationMilliseconds") is not None else None
        words = [_word(w.get("text"), w.get("offsetMilliseconds"),
                       (w.get("offsetMilliseconds") + w.get("durationMilliseconds")) if w.get("offsetMilliseconds") is not None and w.get("durationMilliseconds") is not None else None,
                       j, None) for j, w in enumerate(p.get("words", []))]
        utts.append({"text": p.get("text", ""), "start_ms": start, "end_ms": end, "source_index": i, "words": words})
    return {"text": text, "utterances": utts, "unassigned_words": [], "provider_duration_ms": raw.get("durationMilliseconds"),
            "native_utterances": True, "notes": ["LLM Speech confidence placeholder is not a calibrated score and is dropped"]}


def deepgram(raw: dict) -> dict:
    alt = raw["results"]["channels"][0]["alternatives"][0]

    def word(w, i):
        return _word(w.get("punctuated_word", w.get("word")), _ms(w.get("start"), "seconds"), _ms(w.get("end"), "seconds"), i, w.get("confidence"))
    utts = [{"text": u.get("transcript", ""), "start_ms": _ms(u.get("start"), "seconds"), "end_ms": _ms(u.get("end"), "seconds"),
             "source_index": i, "words": [word(w, j) for j, w in enumerate(u.get("words", []))]}
            for i, u in enumerate(raw["results"].get("utterances", []))]
    channel_words = [word(w, i) for i, w in enumerate(alt.get("words", []))]
    flat = [w for u in utts for w in u["words"]]
    notes = []
    if lexical("".join(w["text"] for w in channel_words)) != lexical("".join(w["text"] for w in flat)):
        notes.append("channel word stream and utterance words disagree lexically")
    return {"text": alt.get("transcript", ""), "utterances": utts, "unassigned_words": [],
            "provider_duration_ms": _ms(raw.get("metadata", {}).get("duration"), "seconds"),
            "native_utterances": bool(utts), "notes": notes}


def soniox(raw: dict) -> dict:
    """Soniox returns a flat token stream (tokens may be sub-words). We keep it as one utterance
    so the same validator applies, and mark that no native segmentation exists."""
    tokens = raw.get("tokens", [])
    words = [_word(t.get("text"), t.get("start_ms"), t.get("end_ms"), i, t.get("confidence")) for i, t in enumerate(tokens)]
    times = [w["start_ms"] for w in words if isinstance(w["start_ms"], (int, float))] + [w["end_ms"] for w in words if isinstance(w["end_ms"], (int, float))]
    utt = {"text": raw.get("text", ""), "start_ms": min(times) if times else None, "end_ms": max(times) if times else None,
           "source_index": 0, "words": words}
    return {"text": raw.get("text", ""), "utterances": [utt] if tokens else [], "unassigned_words": [],
            "provider_duration_ms": None, "native_utterances": False,
            "notes": ["tokens can be sub-words; no native utterance segmentation was returned or invented"]}


NORMALIZERS = {"doubao": doubao, "whisper": whisper, "microsoft": microsoft, "deepgram": deepgram, "soniox": soniox,
               "fake": doubao}


def to_timeline(provider: str, raw: dict) -> dict:
    try:
        fn = NORMALIZERS[provider]
    except KeyError as e:
        raise ValueError(f"no normalizer for provider {provider!r}") from e
    return fn(raw)
