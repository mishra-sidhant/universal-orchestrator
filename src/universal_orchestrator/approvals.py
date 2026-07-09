from __future__ import annotations

from universal_orchestrator.models import (
    ApprovalGate,
    ApprovalReport,
    ContextManifest,
    HostInvocation,
    InputType,
    PrivacyMode,
    ProductContract,
)


class ApprovalGateEngine:
    def evaluate(
        self,
        invocation: HostInvocation,
        manifest: ContextManifest,
        contract: ProductContract,
    ) -> ApprovalReport:
        gates = [
            self._internet_gate(invocation, manifest),
            self._repo_write_gate(invocation, contract),
            self._shell_gate(invocation, manifest, contract),
            self._cloud_gate(invocation),
        ]
        warnings = [
            gate.reason for gate in gates if gate.required and not gate.granted
        ]
        return ApprovalReport(
            run_id=manifest.run_id,
            gates=gates,
            blocked=any(gate.blocking and not gate.granted for gate in gates),
            warnings=warnings,
        )

    def _internet_gate(self, invocation: HostInvocation, manifest: ContextManifest) -> ApprovalGate:
        required = bool(invocation.links) or any(item.type in {InputType.URL, InputType.API} for item in manifest.inputs)
        granted = bool(invocation.user_options.allow_internet)
        return ApprovalGate(
            name="internet_access",
            required=required,
            granted=granted,
            blocking=required,
            severity="high" if required and not granted else "info",
            reason=(
                "Network fetches require explicit allow_internet approval."
                if required and not granted
                else "Network fetch permission is not needed or has been granted."
            ),
        )

    def _repo_write_gate(self, invocation: HostInvocation, contract: ProductContract) -> ApprovalGate:
        required = contract.run_type == "repo_implementation" or "patch" in contract.primary_artifacts
        granted = bool(invocation.user_options.allow_repo_writes)
        return ApprovalGate(
            name="repo_writes",
            required=required,
            granted=granted,
            blocking=False,
            severity="medium" if required and not granted else "info",
            reason=(
                "Repository write actions require allow_repo_writes; deterministic planning remains read-only."
                if required and not granted
                else "Repository writes are not needed or have been granted."
            ),
        )

    def _shell_gate(
        self,
        invocation: HostInvocation,
        manifest: ContextManifest,
        contract: ProductContract,
    ) -> ApprovalGate:
        required = contract.run_type in {"repo_implementation", "code_review"} or any(
            item.type == InputType.REPO for item in manifest.inputs
        )
        granted = bool(invocation.user_options.allow_shell)
        return ApprovalGate(
            name="shell_execution",
            required=required,
            granted=granted,
            blocking=False,
            severity="medium" if required and not granted else "info",
            reason=(
                "Local validation commands require allow_shell; validation plan will be recorded without execution."
                if required and not granted
                else "Shell execution is not needed or has been granted."
            ),
        )

    def _cloud_gate(self, invocation: HostInvocation) -> ApprovalGate:
        privacy_mode = PrivacyMode(invocation.user_options.privacy_mode)
        required = privacy_mode in {PrivacyMode.LOCAL_ONLY, PrivacyMode.EXPLICIT_APPROVAL}
        granted = privacy_mode == PrivacyMode.CLOUD_ALLOWED
        return ApprovalGate(
            name="cloud_provider_execution",
            required=required,
            granted=granted,
            blocking=required,
            severity="high" if required and not granted else "info",
            reason=(
                "Cloud provider execution is blocked by privacy mode."
                if required and not granted
                else "Cloud provider execution is allowed by privacy mode or not requested."
            ),
        )
