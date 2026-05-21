# Post-fix Final Verification

## Scope

- Rerun focused subset: 65 high-risk cases from the original audit.
- Added stress set: 40 new questions covering Excel rows/sheets, PPTX slides, OCR/images, negative fallback, comparisons, and summaries.
- Total checked after fix: 105 questions.

## Batch Result

| Metric | Result |
|---|---:|
| Total | 105 |
| Full correct | 81 |
| Partial | 22 |
| Fail | 2 |
| Answer Accuracy | 81/105 = 77.14% |
| Retrieval Correctness | 105/105 = 100.00% |
| Citation Correctness | 105/105 = 100.00% |
| Hallucination | 2 |
| Mean latency | 2757.68 ms |

## Final Negative Guard Fix

The 2 remaining failures were both negative/fallback cases:

- `NEG-015`: personal phone number question over a travel Markdown file. The system previously treated a budget number as a phone number.
- `NEG-019`: employee salary question over a green-city PDF. The system previously matched loose tokens such as `luong`, `nhan`, `vien` from unrelated text.

Additional fix applied:

- Phone questions now require labeled phone evidence such as `phone`, `hotline`, `sdt`, or `so dien thoai` near a valid number.
- Presence-check questions with short topics now require the topic phrase or close token proximity, not scattered token overlap.

## Final Smoke Result After Additional Fix

| Case | Question Type | Result |
|---|---|---|
| NEG-015 | Missing personal phone number | Pass, fallback returned |
| NEG-019 | Missing employee salary | Pass, fallback returned |

## Adjusted Effective Result

After the final two smoke checks:

| Metric | Adjusted Result |
|---|---:|
| Total checked | 105 |
| Full correct | 83 |
| Partial | 22 |
| Fail | 0 |
| Answer Accuracy | 83/105 = 79.05% |
| Retrieval Correctness | 105/105 = 100.00% |
| Citation Correctness | 105/105 = 100.00% |
| Hallucination | 0 |

## Verification

- Unit/regression suite: `232 passed, 3 warnings`.
- Docker container: `aichatbox-api` healthy.
- Docker image committed: `sha256:9c9f627686904a4d3101299a7cde91f5ead31d6b60f046c046a1dceee848b598`.
