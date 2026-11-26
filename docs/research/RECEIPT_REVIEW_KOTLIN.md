# Receipt OCR review — Kotlin contract (research, not Android UI)

## Verified findings

GitHub Actions [45882617982](https://github.com/georg1995105-hash/FIN-CONTROL/actions/runs/45882617982) completed successfully. Exact same 89 reused real images, machine-generated CDEK reference only. For graph MLP: **36/89** strictly supported total candidates, **53/89** abstentions, **0** mismatches against machine references. Of those 53 refusals, **47** have the machine reference within up to 3 review alternatives; **30** generate a ranked leading suggestion, of which **27** match and **3 do not**. The leading suggestion is NOT safe as an automatic result or preselection. On 120 structured examples, all 60 negative examples were rejected from strict support; manual-review options are distinct from financial approvals.

These are reused, imperfect references. 47/53 is *potential recoverability after manual review*, not achieved financial accuracy or an independent validation.

## Kotlin stage

\`core/src/main/kotlin/fincontrol/core/ReceiptTotalReview.kt\` is a pure JVM UI/domain contract with no network, Android SDK, runtime model or financial auto-approval. Four states: \`SUPPORTED_CANDIDATE\`, \`REVIEW_SUGGESTION\`, \`AMBIGUOUS_REVIEW\`, \`NEEDS_RECAPTURE\`. The rank is only advisory; no option is preselected and every selection requires an explicit gesture. A capture revision invalidates stale confirmations. Every displayed amount is rechecked against its exact original OCR source line; source line coordinates are not per-character boxes. High-confidence source evidence, accepted numeric shape, source ID, duplicate ID and nonfinal tax/payment safeguards are checked. Supported status must originate from the unchanged strict Python \`select\` gate; the Kotlin mode field does **not** make financial conclusions.

A \`UserVerifiedTotal\` is just a confirmed OCR field. It **does not** set \`Receipt.complete=true\` or \`Receipt.confirmed=true\`; no verdict can follow until full line items, discounts, tax basis, currency, rounding, provenance and document completeness are independently verified. Do not copy model scores into financial correctness percentages.

## Required Android integration later

Connect the future offline OCR runtime to a local adapter that translates exact OCR source IDs, normalized amounts, confidence to basis points, and original source-line boxes. Preserve stable per-capture revision, prevent accidental confirmation when the photo changes, display neutral alternatives without recommending the top score as guaranteed, and keep all input locally. The approved nine-screen design remains unchanged. No Android app has been implemented by this commit; next deliverable is the offline import/camera + actual visual review flow, followed by device tests and manually annotated evaluation.

Benchmark metrics are stored as aggregate JSON only; raw images, text and identifiers are not committed.
