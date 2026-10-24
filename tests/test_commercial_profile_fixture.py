from __future__ import annotations

import json
import unittest
from pathlib import Path

from windlens.uncertainty_business import calculate_indicative_value, validate_commercial_profile


PROFILE_PATH = Path("data/derived/commercial_profiles/demo_ppa_profile.json")


class CommercialProfileFixtureTests(unittest.TestCase):
    def test_demo_profile_is_valid_and_calculates_only_an_indicative_value(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        validate_commercial_profile(profile)
        result = calculate_indicative_value(10000.0, profile)
        self.assertEqual(result["claim_scope"], "indicative")
        self.assertIn("Not a settlement", result["disclaimer"])


if __name__ == "__main__":
    unittest.main()
