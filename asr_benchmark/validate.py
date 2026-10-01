"""Internal-consistency checks on a provider timeline.

This measures whether a provider's own output is *structurally usable* — monotonic, inside the audio,
text consistent between levels — not whether it is acoustically correct. Accuracy needs a human
reference transcript and is deliberately left as None in the comparison output.
"""
from __future__ import annotations

import math
from collections import Counter

from .normalize import lexical


def finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(timeline: dict, duration_ms: float | None) -> dict:
    counts: Counter = Counter()
    total = timing_valid = valid = 0
    lexical_total = lexical_valid = formatting_count = formatting_invalid = 0
    details = []
    full_agreement = lexical(timeline["text"]) == lexical("".join(u["text"] for u in timeline["utterances"]))
    if not full_agreement:
        counts["full_text_vs_utterances_mismatch"] += 1
    prev_u_end = prev_w_end = None
    for i, u in enumerate(timeline["utterances"]):
        start, end = u["start_ms"], u["end_ms"]
        issues = []
        if not finite(start) or not finite(end):
            issues.append("missing_or_nonfinite_utterance_time")
        else:
            if end <= start:
                issues.append("nonpositive_utterance_duration")
            if start < 0 or (duration_ms is not None and end > duration_ms):
                issues.append("utterance_outside_audio")
            if prev_u_end is not None and start < prev_u_end:
                issues.append("utterance_overlap_or_nonmonotonic")
            prev_u_end = max(prev_u_end or 0, end)
        text_agreement = lexical(u["text"]) == lexical("".join(w["text"] for w in u["words"]))
        if u["words"] and not text_agreement:
            issues.append("utterance_words_lexical_mismatch")
        counts.update(issues)
        word_results = []
        for j, w in enumerate(u["words"]):
            total += 1
            ws, we = w["start_ms"], w["end_ms"]
            wi = list(w.get("association_issues", []))
            is_lexical = bool(lexical(w["text"]))
            lexical_total += int(is_lexical)
            formatting_count += int(not is_lexical)
            if not finite(ws) or not finite(we):
                wi.append("missing_or_nonfinite_word_time")
            else:
                if we == ws:
                    wi.append("zero_duration_word")
                elif we < ws:
                    wi.append("negative_duration_word")
                if ws < 0 or (duration_ms is not None and we > duration_ms):
                    wi.append("word_outside_audio")
                if finite(start) and finite(end) and (ws < start or we > end):
                    wi.append("word_outside_utterance")
                if prev_w_end is not None and ws < prev_w_end:
                    wi.append("word_overlap_or_nonmonotonic")
                prev_w_end = max(prev_w_end or 0, we)
            timing_ok = not wi and not any(x != "utterance_words_lexical_mismatch" for x in issues)
            timing_valid += int(timing_ok)
            certain = timing_ok and text_agreement and full_agreement
            valid += int(certain)
            lexical_valid += int(certain and is_lexical)
            formatting_invalid += int(not certain and not is_lexical)
            counts.update(wi)
            word_results.append({"index": j, "issues": wi, "usable_timing_evidence": certain,
                                 "token_class": "lexical" if is_lexical else "formatting_only"})
        details.append({"index": i, "issues": issues, "lexical_agreement": text_agreement, "words": word_results,
                        "uncertain": bool(issues) or not full_agreement or any(not w["usable_timing_evidence"] for w in word_results)})
    for w in timeline.get("unassigned_words", []):
        total += 1
        counts["unresolved_word_to_utterance"] += 1
        is_lex = bool(lexical(w["text"]))
        lexical_total += int(is_lex)
        formatting_count += int(not is_lex)
        formatting_invalid += int(not is_lex)
    return {"validation_version": "speech-consistency-v1", "audio_duration_ms": duration_ms,
            "utterance_count": len(timeline["utterances"]), "word_count": total,
            "timing_valid_word_count": timing_valid, "usable_word_count": valid,
            "lexical_token_count": lexical_total, "usable_lexical_token_count": lexical_valid,
            "usable_lexical_token_fraction": lexical_valid / lexical_total if lexical_total else None,
            "formatting_only_token_count": formatting_count, "uncertain_formatting_token_count": formatting_invalid,
            "usable_word_fraction": valid / total if total else None,
            "full_text_utterance_lexical_agreement": full_agreement, "native_utterances": timeline.get("native_utterances", True),
            "issue_counts": dict(counts), "utterances": details,
            "note": "Consistency coverage only, not acoustic accuracy. Raw confidence is not calibrated."}
