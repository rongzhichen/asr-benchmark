# Design notes

## Timeline schema

```json
{
  "text": "full transcript as the provider returned it",
  "provider_duration_ms": 4200,
  "native_utterances": true,
  "utterances": [
    {"text": "…", "start_ms": 120, "end_ms": 1900, "source_index": 0,
     "words": [{"text": "…", "start_ms": 120, "end_ms": 700, "confidence": 0.98, "source_index": 0, "association_issues": []}]}
  ],
  "unassigned_words": [],
  "notes": ["provider-specific caveats"]
}
```

Rules: provider order is preserved; times are converted to milliseconds but never invented; a word the provider returned but
that cannot be placed in an utterance by exact lexical offsets goes to `unassigned_words` rather than to a guessed utterance.

## Why "one attempt per directory"

Retrying inside the tool would make wall-clock numbers and failure rates lies. If a request fails you get a directory that
says so, and you run again into a new directory. The comparison report can then include both.

## Why redaction is applied to the provider's response

Some APIs echo request headers or metadata back in error bodies. A credential in `raw-response.json` would be committed to a
report that is meant to be shared. The redactor runs on everything written, and the test suite includes a provider fixture
that deliberately echoes the key.

## Why accuracy is `null`

Without a reviewed reference transcript, any "accuracy" number would be a comparison between two machines' guesses. The
report says so at the top and leaves CER/WER empty rather than reporting agreement as correctness.
