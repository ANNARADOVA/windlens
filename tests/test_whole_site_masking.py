from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from windlens import evidence_tiers
from windlens.backtest import run_backtest_event
from windlens.run_kelmarsh_whole_site_masking_backtest import (
    NORTH,
    SOUTH,
    assert_no_masked_peer,
    run_whole_site_events,
)

_EPOCH = datetime(2016, 7, 1, tzinfo=timezone.utc)


def _ts(n: int, start_minute: int = 0) -> list[str]:
    return [
        (_EPOCH + timedelta(minutes=start_minute + 10 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in range(n)
    ]


def _fixture():
    """KWF1 (target) and KWF4 (its masked-half peer, a PERFECT copy of KWF1) vs. surviving
    KWF2/KWF3 (noisier). If the mask leaked, KWF4 would be the obvious top reference."""

    rng = np.random.default_rng(7)
    n_pre, n_block = 1200, 6
    pre, block = _ts(n_pre), _ts(n_block, start_minute=20000)
    base = 6.0 + 2.5 * np.sin(np.linspace(0, 40, n_pre)) + rng.normal(0, 0.3, n_pre)
    block_base = np.array([5.0, 5.5, 6.0, 6.5, 7.0, 7.5])
    series = {
        "KWF1": (base, block_base),
        "KWF4": (base.copy(), block_base.copy()),  # perfect peer, but in the masked half
        "KWF2": (base * 0.95 + rng.normal(0, 0.4, n_pre), block_base * 0.95),
        "KWF3": (base * 1.05 + rng.normal(0, 0.4, n_pre), block_base * 1.05),
    }
    frames = []
    for turbine, (pre_speed, block_speed) in series.items():
        for stamps, speed in ((pre, pre_speed), (block, block_speed)):
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp_utc": stamps,
                        "turbine_id": turbine,
                        "wind_speed_ms": speed,
                        "wind_direction_deg": 200.0,
                        "active_power_kw": np.clip(np.asarray(speed) * 150.0, 0, 2050),
                    }
                )
            )
    metadata = pd.DataFrame(
        {
            "turbine_id": ["KWF1", "KWF4", "KWF2", "KWF3"],
            "latitude": [52.4006, 52.3988, 52.4026, 52.4038],
            "longitude": [-0.9471, -0.9412, -0.9495, -0.9442],
        }
    )
    return pd.concat(frames, ignore_index=True), metadata, (block[0], _ts(1, start_minute=20060)[0])


class WholeSiteMaskingTests(unittest.TestCase):
    def test_split_is_a_partition_of_kelmarsh(self) -> None:
        self.assertEqual(set(SOUTH) | set(NORTH), {f"KWF{i}" for i in range(1, 7)})
        self.assertFalse(set(SOUTH) & set(NORTH))

    def test_masked_half_peer_is_never_used_even_when_it_is_the_best_reference(self) -> None:
        df, metadata, block = _fixture()
        # Sanity: with KWF4 allowed it WOULD be chosen (perfect copy), so this test can fail.
        open_event = run_backtest_event(df, "KWF1", ["KWF4", "KWF2", "KWF3"], *block, metadata_df=metadata)
        self.assertIn("KWF4", open_event["ensemble_references"])

        events, _ = run_whole_site_events(df, metadata, ["KWF1", "KWF4"], ["KWF2", "KWF3"], [block])
        self.assertTrue(events)
        for event in events:
            used = {event["baseline_reference"], *event["ensemble_references"]}
            self.assertTrue(used <= {"KWF2", "KWF3"}, used)

    def test_assert_no_masked_peer_raises_on_leak(self) -> None:
        leaky = {"baseline_reference": "KWF4", "ensemble_references": ["KWF2", "KWF4"]}
        with self.assertRaises(AssertionError):
            assert_no_masked_peer(leaky, ["KWF1", "KWF4"], "KWF1")
        ok = {"baseline_reference": "KWF2", "ensemble_references": ["KWF2", "KWF3"]}
        assert_no_masked_peer(ok, ["KWF1", "KWF4"], "KWF1")

    def test_framing_text_is_verbatim_and_never_claims_neighbouring_farm_validation(self) -> None:
        self.assertIn("whole-site masking stress test", evidence_tiers.WHOLE_SITE_FRAMING)
        self.assertIn("best-case ceiling bound", evidence_tiers.WHOLE_SITE_FRAMING)
        self.assertIn("NOT a neighbouring-farm validation", evidence_tiers.WHOLE_SITE_FRAMING)
        self.assertIn(
            "NOT a neighbouring-farm validation", evidence_tiers.CROSS_FARM_FRAMING.format(distance_km=400)
        )


if __name__ == "__main__":
    unittest.main()
