# Capacity And Provider Disposition

| Item | Status | Commit | Evidence |
|---|---|---|---|
| Typed capacity states and windows | fixed | `320fc13` | `tests/test_tranche_g0_capacity.py` |
| Exact reservation cannot overbook remaining capacity | fixed | `320fc13` | CapacityBroker reservation tests |
| Capacity snapshots persist in SQLite | fixed | `320fc13` | Runtime round-trip test |
| HTTP rate-limit headers normalize to snapshots | fixed | `320fc13` | Header parser and adapter tests |
| Gemini API fixture adapter | fixed | `320fc13` | `tests/test_tranche_g1_providers.py` |
| xAI/OpenAI-compatible fixture adapter | fixed | `320fc13` | `tests/test_tranche_g1_providers.py` |
| Capability values are labeled configured priors | fixed | `320fc13` | README, architecture, provider descriptors |
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
| Pre-call capacity reservation blocks known exhausted windows | fixed | `00ccd2c` | `tests/test_tranche_g0_capacity.py` |
| Cross-provider handoff and durable checkpoints | fixed | `17a4df5` | `tests/test_tranche_h1_scheduler.py`, `tests/test_tranche_h2_handoff.py` |
| Optional OCR/transcription connected to rich ingestion | fixed | `76fbf55` | `tests/test_rich_ingestion.py` |
| Strict typing backlog removed without disabled error codes | fixed | `76fbf55` | `mypy src` |
| Product plan persisted and task references validated in real runs | fixed | `8f8826d` | `tests/test_pipeline.py`, `tests/test_tranche_k1_artifacts.py` |
| MCP hosts preserve privacy, budget, URL, shell/write, and artifact controls | fixed | `03357c8` | `tests/test_mcp.py` |
| Expired provider windows reopen as unknown after reset | fixed | `4649b07` | `tests/test_tranche_g0_capacity.py` |
| Gemini, xAI, and OpenAI-compatible health probes use fixture-tested endpoints | fixed | `8df8f43` | `tests/test_tranche_f5.py` |
