"""서로 다른 유효40hex label/ENV를 실제 비교 검사가 거부하는지 검증한다."""

import copy
import unittest

from scripts.check_web_image_provenance import verify_revision

CHECKOUT = "3" * 40
WRONG = "2" * 40


class ImageProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = [{
            "Config": {
                "Labels": {"org.opencontainers.image.revision": CHECKOUT},
                "Env": ["NODE_ENV=production", "PINVI_SOURCE_REVISION=" + CHECKOUT],
            }
        }]

    def test_actual_revision_matches_both_fields(self) -> None:
        verify_revision(self.image, CHECKOUT)

    def test_other_valid_commit_in_oci_label_is_rejected(self) -> None:
        self.image[0]["Config"]["Labels"]["org.opencontainers.image.revision"] = WRONG
        with self.assertRaisesRegex(ValueError, "OCI revision"):
            verify_revision(self.image, CHECKOUT)

    def test_other_valid_commit_in_environment_is_rejected(self) -> None:
        self.image[0]["Config"]["Env"] = ["PINVI_SOURCE_REVISION=" + WRONG]
        with self.assertRaisesRegex(ValueError, "revision ENV"):
            verify_revision(self.image, CHECKOUT)

    def test_same_wrong_commit_in_both_fields_is_rejected(self) -> None:
        self.image[0]["Config"]["Labels"]["org.opencontainers.image.revision"] = WRONG
        self.image[0]["Config"]["Env"] = ["PINVI_SOURCE_REVISION=" + WRONG]
        with self.assertRaises(ValueError):
            verify_revision(self.image, CHECKOUT)

    def test_duplicate_environment_values_are_rejected(self) -> None:
        self.image[0]["Config"]["Env"].append("PINVI_SOURCE_REVISION=" + WRONG)
        with self.assertRaisesRegex(ValueError, "revision ENV"):
            verify_revision(self.image, CHECKOUT)

    def test_exactly_one_image_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            verify_revision(self.image + copy.deepcopy(self.image), CHECKOUT)


if __name__ == "__main__":
    unittest.main()
