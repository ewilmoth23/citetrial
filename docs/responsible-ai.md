# Responsible AI

CiteTrail treats generated prose as a reviewable interpretation, never as the source of record.

- Summaries can omit material context or overstate weak evidence.
- Inferences may be wrong even when every citation marker is valid.
- Citations prove that a passage exists at a stored location; they do not prove truth.
- Multiple publications may repeat the same original error and are not automatically independent.
- Source context signals and extraction quality are not truth scores.
- Timeline extraction may misread the date of publication as the date of an event.
- Approximate dates must not become exact dates.
- Absence of retrieved evidence is not evidence of absence.
- Model-assisted claim and evidence suggestion endpoints are not implemented. Model-suggested timeline
  records accepted through the API require verified evidence and remain pending until user review.
- Contradiction detection identifies disagreement; it does not identify misinformation or choose a winner.
- Users should open excerpts and inspect the surrounding source before relying on generated work.

When no model is available, CiteTrail displays deterministic retrieval rather than inventing a synthesis.
Malformed model output is discarded while deterministic project data remains intact.
