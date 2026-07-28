from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from universal_orchestrator.application_config import (
    AppConfig,
    ConfigPaths,
    ProviderProfile,
    apply_profile_environment,
    initialize,
    load_config,
    migrate_env_file,
    save_config,
)


class ApplicationConfigTests(unittest.TestCase):
    def test_initialize_is_idempotent_and_writes_non_secret_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = ConfigPaths(tmp)
            first = initialize(paths)
            second = initialize(paths)

            self.assertEqual(first.schema_version, 1)
            self.assertEqual(second.schema_version, 1)
            self.assertEqual(load_config(paths).active_profile, "default")
            self.assertIn("schema_version", paths.config_file.read_text())
            self.assertNotIn("planted-secret", paths.config_file.read_text())

    def test_profile_override_is_loaded_without_overwriting_base_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = ConfigPaths(tmp)
            initialize(paths)
            profile = AppConfig(
                active_profile="local",
                privacy_mode="local_only",
                providers={
                    "ollama.local": ProviderProfile(
                        provider_id="ollama.local",
                        model="llama-test",
                    )
                },
            )
            from universal_orchestrator.application_config import save_profile

            save_profile(profile, "local", paths)
            loaded = load_config(paths, profile="local")

            self.assertEqual(loaded.privacy_mode, "local_only")
            self.assertEqual(loaded.providers["ollama.local"].model, "llama-test")
            self.assertEqual(load_config(paths).active_profile, "default")

    def test_env_migration_does_not_copy_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = ConfigPaths(Path(tmp) / "home")
            env_file = Path(tmp) / ".env.local"
            env_file.write_text(
                "OPENAI_API_KEY=planted-secret\nOPENAI_MODEL=test-model\n"
                "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
            )

            config, migrated = migrate_env_file(env_file, paths)
            text = paths.config_file.read_text()

            self.assertIn("OPENAI_MODEL", migrated)
            self.assertIn("OLLAMA_BASE_URL", migrated)
            self.assertEqual(config.providers["openai.configured"].model, "test-model")
            self.assertNotIn("planted-secret", text)

    def test_profile_applies_only_missing_environment_values(self) -> None:
        old_model = os.environ.get("OLLAMA_MODEL")
        os.environ.pop("OLLAMA_MODEL", None)
        try:
            config = AppConfig(
                providers={
                    "ollama.local": ProviderProfile(
                        provider_id="ollama.local", model="profile-model"
                    )
                }
            )
            applied = apply_profile_environment(config)
            self.assertIn("OLLAMA_MODEL", applied)
            self.assertEqual(os.environ["OLLAMA_MODEL"], "profile-model")
        finally:
            if old_model is None:
                os.environ.pop("OLLAMA_MODEL", None)
            else:
                os.environ["OLLAMA_MODEL"] = old_model

    def test_save_config_keeps_cost_ceiling_at_or_above_explicit_operator_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = ConfigPaths(tmp)
            config = AppConfig(cost_ceiling_usd=0.25)
            save_config(config, paths)
            self.assertEqual(load_config(paths).cost_ceiling_usd, 0.25)


if __name__ == "__main__":
    unittest.main()
