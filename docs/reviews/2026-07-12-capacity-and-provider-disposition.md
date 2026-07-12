# Capacity And Provider Disposition

| Item | Status | Commit | Evidence |
|---|---|---|---|
| Typed capacity states and windows | fixed | pending | `tests/test_tranche_g0_capacity.py` |
| Exact reservation cannot overbook remaining capacity | fixed | pending | CapacityBroker reservation tests |
| Capacity snapshots persist in SQLite | fixed | pending | Runtime round-trip test |
| HTTP rate-limit headers normalize to snapshots | fixed | pending | Header parser and adapter tests |
| Gemini API fixture adapter | fixed | pending | `tests/test_tranche_g1_providers.py` |
| xAI/OpenAI-compatible fixture adapter | fixed | pending | `tests/test_tranche_g1_providers.py` |
| Capability values are labeled configured priors | fixed | pending | README, architecture, provider descriptors |
| Subscription CLI execution | fixed | pending | `tests/test_tranche_g2_cli.py` |
| SQLite fenced leases and validated checkpoints | fixed | pending | `tests/test_tranche_h1_scheduler.py` |
| Bounded provider handoff | fixed | pending | `tests/test_tranche_h2_handoff.py` |
| Hybrid retrieval with persistent local vectors | fixed | pending | `tests/test_tranche_i1_retrieval.py` |
| Lexical floor kept distinct from entailment | fixed | pending | `tests/test_tranche_i2_verification.py` |
| Safe archive extraction | fixed | pending | `tests/test_tranche_j1_ingestion.py` |
| OCR/transcription command boundaries | fixed | pending | `tests/test_tranche_j1_ingestion.py` |
| Typed product/chapter/slide plans | fixed | pending | `tests/test_tranche_k1_artifacts.py` |
| PPTX build and structural validation | fixed | pending | `tests/test_tranche_k1_artifacts.py` |
| Cross-provider handoff and durable checkpoints | planned | pending | Tranche H |
