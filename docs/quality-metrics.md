# Quality Metric Provenance

`QualityScore` contains only values computed by the runtime. It does not report factual correctness, semantic entailment, prose style, rendered appearance, or monetary cost because those checks do not currently occur.

| Field | Type | Computed from | Meaning and limits |
| --- | --- | --- | --- |
| `completeness` | 0-100 integer | 40% passed structured validators + 40% successful unique task IDs over the union of planned/executed task IDs + 20% parsed inputs | Capped at 69 when a high/critical violation exists. It measures workflow completion, not answer completeness. |
| `parse_confidence` | 0-100 integer | `parsed_input_count / inventoried_input_count` | Parser success coverage only. It is not factuality. |
| `citation_support` | 0-100 integer | resolved source-evidence-required claims / source-evidence-required claims | Runtime-derived stage measurements explicitly set `evidence_required=false` and do not inflate or depress this score. A source claim resolves only when every ref is an existing, non-injection-risk chunk consumed by that task. It does not measure semantic entailment. |
| `continuity` | 0-100 integer | successful unique task IDs / union of planned and executed task IDs | Includes repair task IDs and cannot exceed 100. |
| `routing_efficiency` | 0-100 integer | decisions using full `ROUTE` / all routing decisions | Penalizes degraded, reshaped, and paused decisions. It is not a cost metric. |
| `artifact_presence` | `pass`/`fail` | non-empty declared artifact list and every listed path exists at evaluation time | Presence only. Hash/size integrity is authoritative in `artifact_integrity_report.json`. |
| `code_validation` | `pass`/`fail`/`not_applicable` | actual allowlisted repository command results | Unexecuted or unavailable validation is never reported as pass. |

## Deliberately Absent

- `factuality`: removed; parser success was not factual verification.
- `style_quality`: removed; file existence was not a style or render check.
- `cost_efficiency`: renamed to `routing_efficiency`; `budget_report.json` now carries estimated dry-run usage, but no live execution evidence supports a cost-effectiveness score.
- `artifact_integrity`: renamed to `artifact_presence` inside `QualityScore`; final cryptographic integrity remains a separate report.
