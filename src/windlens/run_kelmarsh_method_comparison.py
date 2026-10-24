"""Compare wind-first and direct-power reconstruction on the Kelmarsh back-test.

Mirrors compare_reconstruction_methods.py (built for Hill of Towie) on the
Kelmarsh same-farm back-test target (KWF1) and the same 5 pre-declared blocks
used by run_backtest.py. Same-farm caveat: Kelmarsh references are other
turbines on the SAME farm, so this is not external-farm evidence either way --
see docs/DECISION_LOG.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from windlens.checksums import file_md5
from windlens.connectors import KelmarshConnector
from windlens.dynamic_reference import select_dynamic_references
from windlens.loss_estimate import integrate_energy_kwh
from windlens.power_curve import apply_power_curve, fit_power_curve
from windlens.reconstruct import reconstruct_wind_speed

TARGET = "KWF1"
CANDIDATES = ["KWF2", "KWF3", "KWF4", "KWF5", "KWF6"]
BLOCKS = (
    ("2016-05-17T00:00:00Z", "2016-05-22T00:00:00Z"),
    ("2016-05-29T00:00:00Z", "2016-06-03T00:00:00Z"),
    ("2016-06-26T00:00:00Z", "2016-07-01T00:00:00Z"),
    ("2016-07-07T00:00:00Z", "2016-07-12T00:00:00Z"),
    ("2016-07-13T00:00:00Z", "2016-07-18T00:00:00Z"),
)


def _metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    predicted_energy = integrate_energy_kwh(predicted)
    actual_energy = integrate_energy_kwh(actual)
    return {
        "rmse_kw": float(np.sqrt(np.mean((predicted - actual) ** 2))),
        "mae_kw": float(np.mean(np.abs(predicted - actual))),
        "expected_kwh": predicted_energy,
        "actual_kwh": actual_energy,
        "relative_energy_error_pct": float(
            abs(predicted_energy - actual_energy) / max(actual_energy, 1e-9) * 100
        ),
    }


def compare_methods(
    canonical_path: str | Path, metadata_path: str | Path, output_path: str | Path
) -> dict:
    dataset = KelmarshConnector(Path(canonical_path), Path(metadata_path)).load()
    data = dataset.data
    metadata = dataset.registry.to_frame()
    rated_power_kw = float(metadata.loc[metadata.turbine_id == TARGET, "rated_power_kw"].iloc[0])

    blocks = []
    for block_start, block_end in BLOCKS:
        pre = data[data["timestamp_utc"] < block_start]
        selection = select_dynamic_references(
            pre, TARGET, CANDIDATES, metadata, lookback_days=(30, 90, 180), top_k=3
        )
        reference = selection["selected"]
        truth = data[
            (data["turbine_id"] == TARGET)
            & (data["timestamp_utc"] >= block_start)
            & (data["timestamp_utc"] < block_end)
        ].sort_values("timestamp_utc")
        reference_event = data[
            (data["turbine_id"] == reference)
            & (data["timestamp_utc"] >= block_start)
            & (data["timestamp_utc"] < block_end)
        ][["timestamp_utc", "active_power_kw"]]
        event = truth[["timestamp_utc", "active_power_kw"]].merge(
            reference_event, on="timestamp_utc", suffixes=("_target", "_reference")
        ).dropna()
        train = pre[pre["turbine_id"].isin([TARGET, reference])][
            ["timestamp_utc", "turbine_id", "active_power_kw"]
        ].pivot(index="timestamp_utc", columns="turbine_id", values="active_power_kw").dropna()
        train = train.rename(columns={TARGET: "target", reference: "reference"})
        linear = np.polyfit(train["reference"], train["target"], 1)
        direct_linear = np.clip(
            np.polyval(linear, event["active_power_kw_reference"]), 0, rated_power_kw
        )
        masked = data[
            ~(
                (data["turbine_id"] == TARGET)
                & (data["timestamp_utc"] >= block_start)
                & (data["timestamp_utc"] < block_end)
            )
        ]
        reconstruction = reconstruct_wind_speed(masked, TARGET, reference, block_start, block_end)
        power_curve = fit_power_curve(pre[pre["turbine_id"] == TARGET])
        wind_frame = reconstruction[["timestamp_utc"]].copy()
        wind_frame["predicted_power_kw"] = apply_power_curve(
            power_curve, reconstruction["wind_speed_ms_reconstructed"].to_numpy()
        )
        wind_event = wind_frame.merge(
            truth[["timestamp_utc", "active_power_kw"]], on="timestamp_utc"
        ).dropna()
        blocks.append({
            "block_start": block_start,
            "block_end": block_end,
            "reference": reference,
            "selected_window_days": selection["selected_window_days"],
            "direct_linear": _metrics(direct_linear, event["active_power_kw_target"].to_numpy()),
            "wind_first": _metrics(
                wind_event["predicted_power_kw"].to_numpy(),
                wind_event["active_power_kw"].to_numpy(),
            ),
        })

    aggregate = {}
    for method in ("direct_linear", "wind_first"):
        total_actual = sum(block[method]["actual_kwh"] for block in blocks)
        total_abs_error = sum(
            abs(block[method]["expected_kwh"] - block[method]["actual_kwh"]) for block in blocks
        )
        total_bias = sum(block[method]["expected_kwh"] - block[method]["actual_kwh"] for block in blocks)
        aggregate[method] = {
            "energy_weighted_wape_pct": total_abs_error / max(total_actual, 1e-9) * 100,
            "signed_aggregate_bias_pct": total_bias / max(total_actual, 1e-9) * 100,
        }

    artifact = {
        "artifact_version": "method-comparison.v1",
        "farm_id": "Kelmarsh",
        "target_turbine": TARGET,
        "canonical_path": str(canonical_path),
        "canonical_md5": file_md5(Path(canonical_path)),
        "metadata_path": str(metadata_path),
        "metadata_md5": file_md5(Path(metadata_path)),
        "blocks": blocks,
        "aggregate": aggregate,
        "honesty_note": (
            "Kelmarsh references are other turbines on the same farm as the target -- this is a "
            "same-farm comparison, not external-farm evidence either way. See docs/DECISION_LOG.md."
        ),
    }
    Path(output_path).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(compare_methods(args.canonical, args.metadata, args.output), indent=2))


if __name__ == "__main__":
    main()
