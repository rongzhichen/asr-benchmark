import json
from pathlib import Path

from asr_benchmark.cli import main
from asr_benchmark.provenance import verify_checksums
from tests.conftest import FIXTURES

SECRET = "sk-test-secret-key-ABCDEFGH12345678"


def test_run_validate_compare_roundtrip(tmp_path: Path, silent_wav: Path):
    key = tmp_path / "key.txt"
    key.write_text(f"label: {SECRET}\n")
    fixture = tmp_path / "fixture.json"
    raw = json.loads((FIXTURES / "doubao_sample.json").read_text(encoding="utf-8"))
    raw["echo"] = SECRET  # a provider that echoes the credential must not leak it to disk
    fixture.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    run = tmp_path / "run1"
    rc = main(["run", "--provider", "fake", "--audio", str(silent_wav), "--out", str(run), "--key-file", str(key),
               "--fixture", str(fixture), "--label", "fake-A"])
    assert rc == 0
    for name in ("manifest.json", "raw-response.json", "receipt.json", "result.json", "timeline.json",
                 "validation.json", "transcript.txt", "checksums.json", "provenance/versions.json", "clip.wav"):
        assert (run / name).exists(), name
    assert SECRET not in (run / "raw-response.json").read_text(encoding="utf-8")
    assert json.loads((run / "receipt.json").read_text())["credential_echo_redacted"] is True
    assert "sk-test" not in "".join(p.read_text(errors="ignore") for p in run.rglob("*.json"))
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["audio"]["sha256"] and abs(manifest["audio"]["duration_ms"] - 4200) < 1
    assert verify_checksums(run) == []

    # tamper → validate refuses unless drift is allowed
    (run / "transcript.txt").write_text("edited\n")
    assert verify_checksums(run) == ["transcript.txt"]
    try:
        main(["validate", str(run)])
        raise AssertionError("expected refusal")
    except SystemExit as e:
        assert "changed" in str(e)
    assert main(["validate", str(run), "--allow-drift"]) == 0
    assert verify_checksums(run) == []

    # second run + compare
    run2 = tmp_path / "run2"
    assert main(["run", "--provider", "fake", "--audio", str(silent_wav), "--out", str(run2), "--fixture", str(fixture)]) == 0
    out = tmp_path / "cmp"
    assert main(["compare", str(run), str(run2), "--out", str(out), "--title", "t"]) == 0
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "fake-A" in html and "大家好" in html and "<script" not in html
    summary = json.loads((out / "comparison.json").read_text())
    assert summary["accuracy"]["cer"] is None and len(summary["runs"]) == 2


def test_run_refuses_existing_directory(tmp_path: Path, silent_wav: Path):
    out = tmp_path / "exists"
    out.mkdir()
    try:
        main(["run", "--provider", "fake", "--audio", str(silent_wav), "--out", str(out)])
        raise AssertionError
    except SystemExit as e:
        assert "already exists" in str(e)


def test_key_file_must_contain_exactly_one_key(tmp_path: Path):
    from asr_benchmark.providers import REGISTRY
    bad = tmp_path / "k.txt"
    bad.write_text("key-one-AAAAAAAAAAAAAAAAAAAA\nkey-two-BBBBBBBBBBBBBBBBBBBB\n")
    try:
        REGISTRY["doubao"].read_key(bad)
        raise AssertionError
    except ValueError as e:
        assert "exactly one" in str(e)
