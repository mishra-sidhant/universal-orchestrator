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
| Subscription CLI execution | fixed | `c10e4e5` | `tests/test_tranche_g2_cli.py` |
| SQLite fenced leases and validated checkpoints | fixed | `17a4df5` | `tests/test_tranche_h1_scheduler.py` |
| Bounded provider handoff | fixed | `17a4df5` | `tests/test_tranche_h2_handoff.py` |
| Hybrid retrieval with persistent local vectors | fixed | `17a4df5` | `tests/test_tranche_i1_retrieval.py` |
| Lexical floor kept distinct from entailment | fixed | `17a4df5` | `tests/test_tranche_i2_verification.py` |
| Safe archive extraction | fixed | `1560b73` | `tests/test_tranche_j1_ingestion.py` |
| OCR/transcription command boundaries | fixed | `1560b73` | `tests/test_tranche_j1_ingestion.py` |
| Typed product/chapter/slide plans | fixed | `1560b73` | `tests/test_tranche_k1_artifacts.py` |
| PPTX build and structural validation | fixed | `1560b73` | `tests/test_tranche_k1_artifacts.py` |
| Async MCP run start and host polling | fixed | `cdf227f` | `tests/test_mcp.py` |
| Read-only Codex/Claude/VS Code/generic integration output | fixed | `cdf227f` | `tests/test_tranche_l1_host.py` |
| Cross-provider handoff and durable checkpoints | planned | pending | Tranche H |
