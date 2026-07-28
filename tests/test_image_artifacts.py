from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.artifact_builders import ArtifactBuilder


class ImageArtifactTests(unittest.TestCase):
    def test_deterministic_image_is_valid_and_nonblank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "figure.png"
            artifact = ArtifactBuilder().build_image("Title", "Grounded content", path)
            builder = ArtifactBuilder()

            self.assertEqual(artifact.name, "figure.png")
            self.assertEqual(builder.validate_image(path), [])

    def test_corrupt_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "figure.png"
            path.write_bytes(b"not-an-image")

            self.assertTrue(ArtifactBuilder().validate_image(path))


if __name__ == "__main__":
    unittest.main()
