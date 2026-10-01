"""asr-benchmark command line: run one provider on one file, validate a run, compare several runs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import uuid
from pathlib import Path

from . import __version__
from .audio import describe
from .normalize import to_timeline
from .provenance import Redactor, load_json, save_json, sha256_bytes, tool_versions, verify_checksums, write_checksums
from .providers import REGISTRY
from .report import render, write
from .validate import validate

SCHEMA = "asr-benchmark-run-v1"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def cmd_run(a: argparse.Namespace) -> int:
    out: Path = a.out.resolve()
    if out.exists():
        sys.exit(f"{out} already exists; every attempt gets a fresh directory (no silent retries)")
    provider_cls = REGISTRY[a.provider]
    provider = provider_cls()
    key = provider_cls.read_key(a.key_file) if a.key_file else ""
    redactor = Redactor(key)
    audio: Path = a.audio.resolve()
    info = describe(audio)
    out.mkdir(parents=True, mode=0o700)
    (out / "provenance").mkdir()
    shutil.copyfile(audio, out / audio.name)  # the exact bytes sent, kept with the result
    request_id = str(uuid.uuid4())
    manifest = {"schema_version": SCHEMA, "run_id": request_id, "provider": provider.name, "model": provider.model,
                "language": a.language or provider.default_language, "request_options": provider.options(a.language),
                "raw_time_unit": provider.time_unit, "audio": info, "started_at": _now(),
                "automatic_retries": 0, "redirects_followed": False, "label": a.label,
                "note": "No VAD, chunking, alignment, hotwords or fallback added; provider output is stored unmodified."}
    save_json(out / "manifest.json", manifest, redactor)
    save_json(out / "provenance" / "versions.json", tool_versions(), redactor)
    print(f"[{provider.name}] sending one request for {audio.name} ({info['bytes']} bytes); credentials are not logged", flush=True)
    settings = {"endpoint": a.endpoint, "fixture": a.fixture}
    try:
        resp = provider.transcribe(audio, info, key, a.language, **settings)
        raw, redacted = redactor.data(resp.raw)
        (out / "raw-response.json").write_bytes(raw)
        receipt = {"request_id": request_id, "http_status": resp.http_status, "provider_request_id": resp.provider_request_id,
                   "elapsed_seconds": resp.elapsed_seconds, "response_sha256": sha256_bytes(raw),
                   "credential_echo_redacted": redacted, "steps": resp.receipts, "finished_at": _now()}
        result = {"status": "completed" if resp.succeeded else "failed", "http_status": resp.http_status,
                  "elapsed_seconds": resp.elapsed_seconds, "note": resp.note}
    except Exception as error:  # noqa: BLE001 - one attempt; the failure is the result
        receipt = {"request_id": request_id, "error_type": type(error).__name__, "finished_at": _now()}
        result = {"status": "failed", "error_type": type(error).__name__, "error": redactor.text(str(error)),
                  "note": "No automatic retry. The request may still have reached the provider."}
    save_json(out / "receipt.json", receipt, redactor)
    save_json(out / "result.json", result, redactor)
    if result["status"] == "completed":
        _normalize_and_validate(out)
    write_checksums(out)
    print(json.dumps({k: result.get(k) for k in ("status", "http_status", "elapsed_seconds", "error")}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 1


def _normalize_and_validate(run: Path) -> dict:
    manifest = load_json(run / "manifest.json")
    raw = json.loads((run / "raw-response.json").read_text(encoding="utf-8"))
    timeline = to_timeline(manifest["provider"], raw)
    validation = validate(timeline, manifest["audio"].get("duration_ms"))
    save_json(run / "timeline.json", timeline)
    save_json(run / "validation.json", validation)
    (run / "transcript.txt").write_text(timeline["text"] + "\n", encoding="utf-8")
    return validation


def _load_run(run: Path) -> dict:
    manifest = load_json(run / "manifest.json")
    if manifest is None:
        sys.exit(f"{run}: not a run directory (no manifest.json)")
    return {"name": manifest.get("label") or manifest["provider"], "manifest": manifest,
            "result": load_json(run / "result.json", {"status": "unknown"}),
            "timeline": load_json(run / "timeline.json"), "validation": load_json(run / "validation.json"), "path": run}


def cmd_validate(a: argparse.Namespace) -> int:
    run = a.run.resolve()
    drift = verify_checksums(run)
    if drift and not a.allow_drift:
        sys.exit("files changed since the run was recorded: " + ", ".join(drift))
    v = _normalize_and_validate(run)
    write_checksums(run)
    print(json.dumps({k: v[k] for k in ("utterance_count", "word_count", "usable_lexical_token_fraction", "issue_counts")}, ensure_ascii=False))
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    runs = [_load_run(p.resolve()) for p in a.runs]
    out: Path = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    audio_rel = None
    first_audio = runs[0]["path"] / runs[0]["manifest"]["audio"]["file"]
    if first_audio.exists():
        shutil.copyfile(first_audio, out / first_audio.name)
        audio_rel = first_audio.name
    summary = {"schema_version": "asr-benchmark-comparison-v1", "generated_at": _now(),
               "runs": [{"name": r["name"], "path": str(r["path"]), "model": r["manifest"].get("model"),
                         "status": r["result"].get("status"), "elapsed_seconds": r["result"].get("elapsed_seconds"),
                         "validation": {k: v for k, v in (r["validation"] or {}).items() if k != "utterances"}} for r in runs],
               "accuracy": {"cer": None, "wer": None, "note": "requires a human reference transcript; not measured"},
               "limitations": ["One file cannot establish reliability.", "Providers received different containers/encodings where noted in manifests.",
                               "Token counts and validity fractions are structural coverage, not accuracy."]}
    save_json(out / "comparison.json", summary)
    write(out / "report.html", render(runs, a.title, audio_rel))
    write_checksums(out)
    print(f"wrote {out / 'report.html'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="asr-benchmark", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="send one audio file to one provider, once, and record everything")
    r.add_argument("--provider", required=True, choices=sorted(REGISTRY))
    r.add_argument("--audio", required=True, type=Path)
    r.add_argument("--out", required=True, type=Path, help="new directory for this attempt")
    r.add_argument("--key-file", type=Path, help="file containing exactly one API key (never passed on the command line)")
    r.add_argument("--language", help="BCP-47 tag, e.g. zh-CN; provider default if omitted")
    r.add_argument("--endpoint", default="", help="microsoft: https://<resource>.cognitiveservices.azure.com")
    r.add_argument("--fixture", default="", help="fake provider: path to a saved raw response")
    r.add_argument("--label", help="display name for reports (default: provider)")
    r.set_defaults(fn=cmd_run)
    v = sub.add_parser("validate", help="re-normalise and re-validate a saved run (offline)")
    v.add_argument("run", type=Path)
    v.add_argument("--allow-drift", action="store_true", help="proceed even if files changed since recording")
    v.set_defaults(fn=cmd_validate)
    c = sub.add_parser("compare", help="side-by-side report for several runs (offline)")
    c.add_argument("runs", nargs="+", type=Path)
    c.add_argument("--out", required=True, type=Path)
    c.add_argument("--title", default="ASR provider comparison")
    c.set_defaults(fn=cmd_compare)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
