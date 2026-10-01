"""HTML report for one or more runs. Static, self-contained, no scripts, no network."""
from __future__ import annotations

import html
import json
from pathlib import Path

CSS = ("body{font:16px system-ui;max-width:1450px;margin:30px auto;padding:0 24px;color:#202124}"
       "table{width:100%;border-collapse:collapse;margin:12px 0}td,th{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}"
       "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:14px}.grid{display:grid;gap:24px;grid-template-columns:repeat(auto-fit,minmax(380px,1fr))}"
       ".warn{background:#fff2d0;padding:14px;border-radius:8px}summary{cursor:pointer}audio{width:100%}")


def _e(x) -> str:
    return html.escape(str(x))


def _row(label, values):
    return "<tr><td>" + _e(label) + "</td>" + "".join("<td>" + _e(v) + "</td>" for v in values) + "</tr>"


def render(runs: list[dict], title: str, audio_rel: str | None = None) -> str:
    """`runs` = [{"name", "manifest", "result", "timeline", "validation"}] — timeline/validation may be None."""
    names = [r["name"] for r in runs]
    page = [f"<!doctype html><html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)}</title><style>{CSS}</style><h1>{_e(title)}</h1>",
            "<p class='warn'>Recognition accuracy is <b>not</b> scored here: there is no human reference transcript. "
            "The checks below detect internal inconsistencies in each provider's own timestamps and text (coverage), "
            "not acoustic correctness. Provider tokenisation differs, so counts are not comparable as accuracy.</p>"]
    if audio_rel:
        page.append(f"<audio controls preload='none' src='{_e(audio_rel)}'></audio>")
    page.append("<table><tr><th>Measure</th>" + "".join(f"<th>{_e(n)}</th>" for n in names) + "</tr>")
    def v(r, key, default="—"):
        return (r.get("validation") or {}).get(key, default)
    page.append(_row("Model", [r["manifest"].get("model", "") for r in runs]))
    page.append(_row("Status", [r["result"].get("status", "") for r in runs]))
    page.append(_row("Request wall-clock (s)", [round(r["result"].get("elapsed_seconds", 0), 2) for r in runs]))
    page.append(_row("Native utterances", [v(r, "native_utterances") for r in runs]))
    page.append(_row("Utterances", [v(r, "utterance_count") for r in runs]))
    page.append(_row("Token entries", [v(r, "word_count") for r in runs]))
    page.append(_row("Lexical tokens", [v(r, "lexical_token_count") for r in runs]))
    page.append(_row("Usable lexical timing evidence", [f"{v(r,'usable_lexical_token_count')}/{v(r,'lexical_token_count')}" if r.get("validation") else "—" for r in runs]))
    page.append(_row("Usable lexical fraction", [round(v(r, "usable_lexical_token_fraction") or 0, 3) if r.get("validation") and v(r, "usable_lexical_token_fraction") is not None else "—" for r in runs]))
    page.append(_row("Issue counts", [json.dumps(v(r, "issue_counts", {}), ensure_ascii=False) for r in runs]))
    page.append("</table><h2>Recognised text</h2><div class='grid'>")
    for r in runs:
        text = (r.get("timeline") or {}).get("text") or r["result"].get("note") or "(no transcript)"
        page.append(f"<section><h3>{_e(r['name'])}</h3><pre>{_e(text)}</pre></section>")
    page.append("</div><h2>Segmentation and word timestamps</h2><p>Columns are independent; rows are not asserted to be equivalent segments. Times in ms.</p><div class='grid'>")
    for r in runs:
        page.append(f"<section><h3>{_e(r['name'])}</h3>")
        tl, val = r.get("timeline"), r.get("validation")
        if not tl:
            page.append("<p>No timeline.</p></section>")
            continue
        for i, u in enumerate(tl["utterances"]):
            flag = " ⚠ uncertain" if val and val["utterances"][i]["uncertain"] else ""
            snippet = (u["text"] or "")[:160]
            head = f"{i + 1}. [{u['start_ms']} → {u['end_ms']}] {snippet}"
            body = json.dumps({"utterance": u, "validation": val["utterances"][i] if val else None}, ensure_ascii=False, indent=2)
            page.append("<details><summary>" + _e(head) + flag + "</summary><pre>" + _e(body) + "</pre></details>")
        page.append("</section>")
    page.append("</div><h2>Provenance</h2><div class='grid'>")
    for r in runs:
        page.append(f"<section><h3>{_e(r['name'])}</h3><pre>{_e(json.dumps(r['manifest'], ensure_ascii=False, indent=2))}</pre></section>")
    page.append("</div></html>")
    return "\n".join(page)


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
