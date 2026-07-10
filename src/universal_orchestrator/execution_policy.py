from __future__ import annotations

from universal_orchestrator.models import (
    ContextManifest,
    EgressDecision,
    ExecutionPolicy,
    HostInvocation,
    InputType,
    PrivacyMode,
    ProviderDescriptor,
    ProviderKind,
)


PRIVATE_INPUT_TYPES = {
    InputType.PROMPT,
    InputType.TEXT,
    InputType.MARKDOWN,
    InputType.PDF,
    InputType.DOCX,
    InputType.PPTX,
    InputType.SPREADSHEET,
    InputType.IMAGE,
    InputType.FOLDER,
    InputType.REPO,
    InputType.ARCHIVE,
    InputType.AUDIO_VIDEO,
    InputType.CODE,
    InputType.UNKNOWN,
}


class PolicyCompiler:
    def compile(self, invocation: HostInvocation, manifest: ContextManifest) -> ExecutionPolicy:
        privacy_mode = PrivacyMode(invocation.user_options.privacy_mode)
        explicit_cloud_permission = bool(invocation.user_options.allow_cloud)
        allow_hosted_models = privacy_mode != PrivacyMode.LOCAL_ONLY and (
            privacy_mode == PrivacyMode.CLOUD_ALLOWED or explicit_cloud_permission
        )
        private_input_ids = sorted(
            item.id
            for item in manifest.inputs
            if item.type in PRIVATE_INPUT_TYPES or item.security_findings
        )
        allow_private_data_egress = allow_hosted_models
        return ExecutionPolicy(
            run_id=manifest.run_id,
            privacy_mode=privacy_mode,
            allow_network_fetch=invocation.user_options.allow_internet,
            allow_hosted_models=allow_hosted_models,
            allow_private_data_egress=allow_private_data_egress,
            allow_shell=invocation.user_options.allow_shell,
            allow_repo_writes=invocation.user_options.allow_repo_writes,
            private_input_ids=private_input_ids,
            decisions=[
                EgressDecision(
                    subject="network_fetch",
                    allowed=invocation.user_options.allow_internet,
                    reason="Controlled independently from hosted-model execution.",
                ),
                EgressDecision(
                    subject="hosted_model_execution",
                    allowed=allow_hosted_models,
                    reason=self._cloud_reason(privacy_mode, explicit_cloud_permission),
                    input_ids=private_input_ids if allow_private_data_egress else [],
                ),
            ],
        )

    def provider_allowed(self, policy: ExecutionPolicy, provider: ProviderDescriptor) -> tuple[bool, str]:
        if provider.kind == ProviderKind.HOSTED_MODEL and not policy.allow_hosted_models:
            return False, f"Hosted provider blocked by privacy mode {policy.privacy_mode}."
        return True, "Provider kind is allowed by execution policy."

    def _cloud_reason(self, privacy_mode: PrivacyMode, explicit_cloud_permission: bool) -> str:
        if privacy_mode == PrivacyMode.LOCAL_ONLY:
            return "Local-only privacy mode prohibits hosted-model execution."
        if privacy_mode == PrivacyMode.CLOUD_ALLOWED:
            return "Cloud-allowed privacy mode permits hosted-model execution."
        if explicit_cloud_permission:
            return "Explicit cloud permission permits hosted-model execution."
        return "Hosted-model execution requires explicit cloud permission."
