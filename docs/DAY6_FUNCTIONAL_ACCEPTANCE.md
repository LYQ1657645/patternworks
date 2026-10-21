# Day 6 functional acceptance — 2026-10-18

This pass follows the user's request to finish functionality before recording or GitHub delivery. It rechecked the original [assessment brief](https://drive.google.com/file/d/17dskAyCYFGbcwX_7yo-VHqpEl14zeciK/view). Video, repository creation and publication are deferred.

## Requirement gap and correction

The original React requirement includes a user-specified replacement value. The earlier regex interface required embedding that value in the natural-language prompt. The regex form now provides **Replacement value** separately.

- The field takes priority over a model-suggested replacement, preserving whitespace and literal Unicode, dollar signs and backslashes. Empty text deletes matches. The maximum is 256 characters, checked before queueing.
- The API stores the selected replacement in the generation job. The worker uses it for the actual preview and the saved, validated rule. Retries retain the same value. Queue messages still contain only job IDs.
- Only the natural-language instruction is sent to OpenAI. The separate replacement field is not sent. The model can handle a pattern-only request such as `Find all email addresses in this column.`
- The validated model pattern cache remains scoped to owner, instruction, model and policy versions. Changing only the literal replacement reuses the pattern; it does not replace the cached model response with another user's chosen value.
- Editing a prompt, column or replacement disables applying a stale preview. Generate again to review the new preview before applying. Restored rules restore the matching replacement value.
- Descriptions for explicit replacements are generated locally from the actual replacement behavior, preventing a cached model explanation from incorrectly describing deletion or another marker.
- Omitted replacement remains supported for existing API clients and saved rules. No database migration or dependency change was needed.

## Verification

The final local backend image passed **211 tests in 17.89 seconds**, including five real Spark tests. The Spark regex integration now exercises queued rule generation with an explicit literal replacement before applying it across partitions. Additional regressions cover blank/whitespace/Unicode/dollar/backslash values, cache independence, API validation, queued execution and manual retry. Django system checks and migration consistency passed. The TypeScript/Vite production build passed in Docker.

The final cloud backend image also passed **211 tests in 59.07 seconds**, including the five real Spark tests. Eight production services are running; backend, PostgreSQL and Redis health checks passed. The public frontend serves the new replacement input over trusted HTTPS. The final live UI and read-only persisted-output audit passed as described below.

## Live functional result

Safari verified the new field, natural-language-only pattern description, literal replacement previews, blank deletion, and disabling Apply after a replacement edit. Five generations of the same pattern request used **one real model call followed by four cache hits**, across different replacement values. The final description accurately reflects the selected literal replacement.

Final public Spark application: job `17610b54-5bac-4d3f-b9c5-ed0c9fdcc124`, SUCCESS; result `ac89b88d-3fb0-4a4f-b2dd-a437c02dd6f3`, eight rows / six columns / four Parquet partitions, three matched rows / four matches / three changed rows.

An independent read-only server audit compared all persisted page cells against explicit expected fixture values, including leading/trailing spaces, `$1`, a backslash and Chinese text. Original source cells matched the CSV fixture, row IDs 1–8 appeared exactly once using three-row cursor pages, and all five previously accepted datasets retained their original ordered digests. This audit checks saved page contents and Parquet partition presence, without making new S3/model calls. [Machine-readable evidence](day6-functional-evidence.json).

## Deployment identity

The existing AWS instance and its private configuration/data volumes are retained. Six source files were updated; prior source files and application images were saved for rollback. The base deployment archive remains unchanged.

- Initial six-file patch SHA-256: `6d0ddb11f6dccd7729d67d1330307f9b794f87e750220a4a977088a8c2a5502e`.
- Follow-up explanation correction SHA-256: `4dc5fbf7403474923d4191a465336e19d53a8597ffc73fa43da58349f1ab7c7f` (two of those files).
- Source changes: `backend/processing/serializers.py`, `views.py`, `tasks.py`, `services/rules.py`, `backend/tests/test_rules.py`, `frontend/src/RulePanel.tsx`.

Existing million-row and failure-injection records remain historical Day 5 evidence. This small replacement-interface correction does not establish new million-row timings. See [cloud acceptance](DEPLOYMENT_ACCEPTANCE.md) and [local scale/recovery evidence](DAY5_ACCEPTANCE.md) for scope and limits.
