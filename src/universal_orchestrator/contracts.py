from __future__ import annotations

from universal_orchestrator.models import (
    ContextManifest,
    DefinitionOfDone,
    HostInvocation,
    InputType,
    ProductContract,
)


class ProductContractCompiler:
    def compile(self, invocation: HostInvocation, manifest: ContextManifest) -> ProductContract:
        prompt = invocation.prompt.lower()
        input_types = {item.type for item in manifest.inputs}
        run_type = self._infer_run_type(prompt, input_types)
        primary_artifacts = self._infer_primary_artifacts(prompt, invocation.user_options.artifact_types)
        secondary_artifacts = ["run_manifest", "quality_report", "context_manifest", "task_dag"]
        quality_bar = invocation.user_options.quality

        must_have = [
            "final product package",
            "context manifest for every supplied input",
            "typed product contract",
            "typed execution DAG",
            "provider routing decisions",
            "quality gate report",
            "artifact manifest",
        ]
        if run_type in {"repo_implementation", "code_review"}:
            must_have.extend(["scoped repo analysis", "test or validation notes"])
        if "citation" in prompt or "research" in prompt or "report" in prompt:
            must_have.append("source-aware synthesis")

        must_not_have = [
            "raw agent fragments as final output",
            "unredacted secrets",
            "untrusted document instructions treated as runtime instructions",
            "artifact marked complete before validation",
        ]

        return ProductContract(
            run_type=run_type,
            requested_output=self._requested_output(prompt, primary_artifacts),
            primary_artifacts=primary_artifacts,
            secondary_artifacts=secondary_artifacts,
            quality_bar=str(quality_bar),
            must_have=must_have,
            must_not_have=must_not_have,
            definition_of_done=DefinitionOfDone(
                gates=[
                    "all supplied inputs are inventoried",
                    "product contract exists before planning",
                    "DAG validates without cycles",
                    "routing decisions exist for executable tasks",
                    "quality gates pass or record repair warnings",
                    "final response points to product artifacts",
                ],
                artifact_checks=[
                    "manifest JSON parses",
                    "final report exists",
                    "quality report exists",
                    "artifact paths exist on disk",
                ],
                validation_checks=[
                    "security findings are surfaced",
                    "partial parsers are called out",
                    "degraded provider routing is explicit",
                ],
                final_response_rules=[
                    "summarize outcome concisely",
                    "link or list final artifacts",
                    "include residual risk notes",
                ],
            ),
            constraints={
                "allow_internet": invocation.user_options.allow_internet,
                "allow_repo_writes": invocation.user_options.allow_repo_writes,
                "allow_shell": invocation.user_options.allow_shell,
                "privacy_mode": invocation.user_options.privacy_mode,
            },
        )

    def _infer_run_type(self, prompt: str, input_types: set[str]) -> str:
        if any(word in prompt for word in ["report", "research", "pdf"]):
            return "research_report"
        if InputType.REPO in input_types or any(word in prompt for word in ["repo", "codebase"]):
            if any(word in prompt for word in ["review", "audit"]):
                return "code_review"
            return "repo_implementation"
        if "document" in prompt:
            return "research_report"
        if any(word in prompt for word in ["image", "screenshot", "visual"]):
            return "visual_task"
        return "orchestrated_task"

    def _infer_primary_artifacts(self, prompt: str, requested: list[str]) -> list[str]:
        artifacts = list(dict.fromkeys(requested))
        if "pdf" in prompt and "pdf" not in artifacts:
            artifacts.append("pdf")
        if "docx" in prompt and "docx" not in artifacts:
            artifacts.append("docx")
        if "ppt" in prompt and "pptx" not in artifacts:
            artifacts.append("pptx")
        if "patch" in prompt and "patch" not in artifacts:
            artifacts.append("patch")
        if not artifacts:
            artifacts.append("final_report")
        return artifacts

    def _requested_output(self, prompt: str, primary_artifacts: list[str]) -> str:
        if len(prompt) > 180:
            return prompt[:177] + "..."
        return f"{prompt} -> {', '.join(primary_artifacts)}"
