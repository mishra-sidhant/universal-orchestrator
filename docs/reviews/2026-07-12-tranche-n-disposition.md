# Tranche N Disposition

Review baseline: Sol review of Tranche M at commit `5c9c1e5`. Every row below is accepted and is a required implementation item unless explicitly marked deferred.

| Finding | Status | Evidence |
| --- | --- | --- |
| ZIP validation can issue a receipt after failure | pending | Tranche N.1 failing-first regression and finalization evidence |
| Default pipeline does not bind SQLite to the capacity broker | pending | Tranche N.2 runtime-binding regression |
| Committed capacity can be reused against stale snapshots | pending | Tranche N.2 sequential reservation regression |
| Headerless observations can erase exact capacity windows | pending | Tranche N.2 observation-merge regression |
| Chapter tasks produce indistinguishable generic output | pending | Tranche N.5 differentiated chapter fixture |
| Render validation inspects only the first page/slide | pending | Tranche N.6 multi-page render mutation |
| Exhausted handoff candidates do not use grounded fallback | pending | Tranche N.3 provider-exhaustion fixture |
| Claim verification receives unconsumed chunks | pending | Tranche N.4 verifier-input fixture |
| Contradicted claims remain citation-eligible | pending | Tranche N.4 citation mutation fixture |
| Live provider quality and semantic entailment | explicitly deferred | Requires operator smoke/bench and an explicitly configured semantic verifier |
