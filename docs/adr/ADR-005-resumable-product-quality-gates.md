# ADR-005: Resumable Execution And Product Quality Gates

- Status: Accepted
- Date: 2026-07-12
- Scope: checkpoint recovery, chapter planning, evidence verification, and artifact delivery

## Decision

Validated task checkpoints are reusable only when all of the following hold: the task is cacheable, the checkpoint schema is known, and the scheduler's exact execution fingerprint matches the current task, context, policy, provider, and routing inputs. The scheduler records checkpoint hits distinctly from filesystem cache hits. Non-cacheable or side-effecting tasks, including artifact builders, are always rerun on resume. Expired leases are abandoned before recovery begins, and late owners cannot commit through the SQLite lease fence.

The product plan is executable. Gap analysis fans out into the executive synthesis, findings/evidence, and risks/actions chapter tasks; artifact construction depends on all chapter tasks. Chapter outputs use the same bounded context and evidence audit as the primary synthesis. A chapter is not considered delivered merely because a product-plan JSON file exists.

Claim verification is an injectable boundary. The default structural verifier resolves chunk references and emits a weak lexical-overlap warning while reporting semantic status as `unknown`; it never claims entailment. A configured verifier may report supported, insufficient, or contradicted. Contradictions block the evidence audit and delivery; unknown remains explicitly unknown.

Artifact validation has two layers. Structural corruption always blocks. Render-level failures and renderer unavailability block serious/max quality bars and become warnings for fast/standard runs. A delivery receipt is issued only after the final quality result includes these artifact findings.

## Consequences

- Resume is deterministic and does not silently replay completed pure work.
- A chapter plan is coupled to real execution dependencies and independent outputs.
- The default system remains honest without a semantic model or desktop renderer.
- Operators can choose a lower quality tier when tooling is intentionally unavailable, but the artifact and audit record says what was not proven.
