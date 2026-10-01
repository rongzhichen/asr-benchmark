# asr-benchmark

**Compare speech-to-text providers on the same audio, with evidence you can hand to someone else.**

Send one file to one provider, once. Keep the exact bytes you sent, the exact bytes you got back, who/when/how, and a checksum of all of it. Normalise every provider's output into one timeline schema, check it for *internal* consistency, and render a side-by-side report — without pretending to measure accuracy you haven't measured.

Extracted from the provider evaluation I ran while choosing the Mandarin transcription backend for [Telltake](https://telltake.com) (Doubao vs. Whisper vs. Microsoft LLM Speech vs. Deepgram vs. Soniox). Python 3.10+, standard library only.

```sh
pip install -e ".[dev]"            # or: pipx install .

asr-benchmark run --provider doubao  --audio clip.wav --out runs/doubao  --key-file ~/.keys/doubao
asr-benchmark run --provider whisper --audio clip.m4a --out runs/whisper --key-file ~/.keys/openai --language zh
asr-benchmark run --provider soniox  --audio clip.wav --out runs/soniox  --key-file ~/.keys/soniox
asr-benchmark compare runs/doubao runs/whisper runs/soniox --out runs/report --title "Clip 1 · Mandarin"
open runs/report/report.html
```

## Why it exists

Choosing an ASR vendor from a few demo clips goes wrong in predictable ways: the file you sent to vendor A wasn't quite the file you sent to vendor B; someone retried a failed call and the "latency" is the second attempt; the raw response got lost and only a pasted transcript remains; and word-level timestamps that *looked* fine were overlapping or outside the audio. This tool makes each of those impossible or visible:

| Principle | What the tool does |
|---|---|
| **One attempt, recorded** | A run directory is created once and never reused; there are no automatic retries and redirects are refused. A failure is a result, not an exception to hide. |
| **Bytes, not summaries** | The audio file is copied into the run, hashed, and described (duration, rate, channels). The provider's raw response is stored unmodified. |
| **Credentials never touch disk** | Keys come from a file containing exactly one key, are held in memory, and are redacted from anything written — including a provider that echoes them back. |
| **Tamper-evident** | `checksums.json` covers every file; `validate` refuses to proceed if anything changed since recording (unless you say `--allow-drift`). |
| **Consistency ≠ accuracy** | The validator reports structural problems (overlaps, non-monotonic times, zero/negative durations, text that disagrees between levels). CER/WER stay `null` until a human reference exists. |
| **Nothing is repaired** | Missing times stay missing. Whisper words are matched to segments by exact lexical offsets, never by guessing from timestamps. Sub-word token streams (Soniox) are kept as-is and flagged as lacking native segmentation. |

## What a run produces

```
runs/doubao/
  clip.wav              the exact audio sent
  manifest.json         provider, model, options, language, audio facts (sha256, duration), start time, run id
  raw-response.json     provider payload, byte-for-byte (credential echoes redacted)
  receipt.json          HTTP status, provider request id, wall-clock, per-step receipts for multi-call providers
  result.json           completed | failed, with the error type if any
  timeline.json         provider output in the common schema (utterances → words, ms)
  validation.json       consistency report (see below)
  transcript.txt        plain text
  provenance/versions.json   tool, Python, ffmpeg, git commit
  checksums.json        sha256 of everything above
```

`compare` writes `comparison.json` plus a static `report.html` (no scripts, no external requests): a measures table, each provider's full text side by side, expandable per-utterance timing with ⚠ on anything uncertain, and every manifest.

## Providers

| `--provider` | Service | Notes |
|---|---|---|
| `doubao` | ByteDance / Volcengine Doubao Turbo (`volc.bigasr.auc_turbo`) | PCM WAV input; punctuation on, ITN and semantic smoothing off |
| `whisper` | OpenAI `whisper-1` | verbose JSON with segment + word timestamps |
| `microsoft` | Azure AI Speech, LLM Speech enhanced mode (`2025-10-15`) | needs `--endpoint https://<resource>.cognitiveservices.azure.com`; confidence is not a score |
| `deepgram` | Deepgram Nova-3, pre-recorded | utterances on, smart formatting off, model-improvement opt-out |
| `soniox` | Soniox `stt-async-v5` | upload → create → poll → download → **delete**; receipts for each step |
| `fake` | local fixture | for tests and demos: `--fixture path/to/raw.json` |

Adding a provider is one file in `asr_benchmark/providers/` (subclass `Provider`, implement `transcribe`) plus a normaliser in `normalize.py` that maps its payload onto the common timeline. Register it in `providers/__init__.py`.

## The consistency validator

For every utterance and word: finite times; `end > start` (zero-duration flagged, negative flagged); inside the audio; monotonic and non-overlapping; words inside their utterance; and text agreement at three levels (full text ↔ utterances ↔ words, compared on `lexical()` form — NFC-normalised, no whitespace or punctuation). Punctuation-only tokens are counted separately as *formatting* so a provider that emits "，" with zero duration isn't penalised on its real words. The headline numbers are `usable_lexical_token_fraction` and `issue_counts`; `validation_version` is recorded so results stay comparable as the rules evolve.

## Layout

```
asr_benchmark/
  cli.py          run / validate / compare
  providers/      base.py + one adapter per vendor + fake.py
  normalize.py    raw payload → common timeline; lexical()
  validate.py     consistency checks
  report.py       static HTML
  provenance.py   hashing, redaction, checksums, tool versions
  http.py         single guarded request: no redirects, timing, status
  audio.py        WAV facts via stdlib; ffprobe if available
tests/            14 tests incl. an end-to-end run→validate→compare with a credential-echo check
```

## Development

```sh
pip install -e ".[dev]"
ruff check . && pytest -q
```

CI runs the same on Python 3.10 and 3.12.

## Limitations

- Measures structure and latency, not recognition accuracy. Add a human reference and a CER/WER step before drawing quality conclusions.
- One clip cannot establish reliability; run several and compare `issue_counts` across them.
- Providers accept different containers; convert to PCM WAV first (`ffmpeg -i in.m4a -c:a pcm_s16le out.wav`) when you want identical inputs, and the manifest will show it.
- Pricing is not captured; add your own rate card to `comparison.json` if you need cost per minute.

## Licence

MIT.
