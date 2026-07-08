import os
import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.config import env_file_presence, load_env_file, provider_config_status


class ConfigTests(unittest.TestCase):
    def test_env_file_presence_reports_keys_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.local"
            env_file.write_text("OPENAI_API_KEY=secret\nOPENAI_MODEL=model\nEMPTY=\n")

            presence = env_file_presence(env_file)

        self.assertTrue(presence["OPENAI_API_KEY"])
        self.assertTrue(presence["OPENAI_MODEL"])
        self.assertFalse(presence["EMPTY"])
        self.assertNotIn("secret", str(presence))

    def test_provider_status_can_use_env_file_without_exporting_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.local"
            env_file.write_text("OPENAI_API_KEY=secret\nOPENAI_MODEL=model\n")

            status = provider_config_status(env_file)

        self.assertTrue(status["openai.configured"]["ready"])
        self.assertNotIn("secret", str(status))

    def test_load_env_file_does_not_override_existing_environment(self) -> None:
        old_value = os.environ.get("OPENAI_MODEL")
        os.environ["OPENAI_MODEL"] = "existing"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_file = Path(tmp) / ".env.local"
                env_file.write_text("OPENAI_MODEL=file-value\n")

                load_env_file(env_file)

            self.assertEqual(os.environ["OPENAI_MODEL"], "existing")
        finally:
            if old_value is None:
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = old_value


if __name__ == "__main__":
    unittest.main()

