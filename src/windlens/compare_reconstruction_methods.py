"""Compare wind-first and direct-power reconstruction on held-out blocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from windlens.checksums import file_md5
from windlens.dynamic_reference import select_dynamic_references
from windlens.loss_estimate import integrate_energy_kwh
from windlens.power_curve import apply_power_curve, fit_power_curve
from windlens.reconstruct import reconstruct_wind_speed


BLOCKS = (
    ("2026-03-01T00:00:00Z", "2026-03-06T00:00:00Z"),
    ("2026-04-01T00:00:00Z", "2026-04-06T00:00:00Z"),
    ("2026-04-15T00:00:00Z", "2026-04-20T00:00:00Z"),
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


def compare_methods(canonical_path: str | Path, registry_path: str | Path, output_path: str | Path) -> dict:
    data = pd.read_csv(canonical_path)
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    metadata = pd.read_csv(registry_path)
    target = "T01"
    candidates = [turbine for turbine in sorted(data["turbine_id"].unique()) if turbine != target]
    blocks = []
    for block_start, block_end in BLOCKS:
        pre = data[data["timestamp_utc"] < block_start]
        selection = select_dynamic_references(
            pre, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3
        )
        reference = selection["selected"]
        truth = data[
            (data["turbine_id"] == target)
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
        train = pre[pre["turbine_id"].isin([target, reference])][
            ["timestamp_utc", "turbine_id", "active_power_kw"]
        ].pivot(index="timestamp_utc", columns="turbine_id", values="active_power_kw").dropna()
        train = train.rename(columns={target: "target", reference: "reference"})
        linear = np.polyfit(train["reference"], train["target"], 1)
        quadratic = np.polyfit(train["reference"], train["target"], 2)
        direct_linear = np.clip(np.polyval(linear, event["active_power_kw_reference"]), 0, 2300)
        direct_quadratic = np.clip(np.polyval(quadratic, event["active_power_kw_reference"]), 0, 2300)
        masked = data[
            ~(
                (data["turbine_id"] == target)
                & (data["timestamp_utc"] >= block_start)
                & (data["timestamp_utc"] < block_end)
            )
        ]
        reconstruction = reconstruct_wind_speed(masked, target, reference, block_start, block_end)
        power_curve = fit_power_curve(pre[pre["turbine_id"] == target])
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
            "direct_quadratic": _metrics(direct_quadratic, event["active_power_kw_target"].to_numpy()),
            "wind_first": _metrics(
                wind_event["predicted_power_kw"].to_numpy(),
                wind_event["active_power_kw"].to_numpy(),
            ),
        })
    artifact = {
        "artifact_version": "method-comparison.v1",
        "farm_id": "Hill of Towie",
        "target_turbine": target,
        "canonical_path": str(canonical_path),
        "canonical_md5": file_md5(Path(canonical_path)),
        "registry_path": str(registry_path),
        "registry_md5": file_md5(Path(registry_path)),
        "blocks": blocks,
        "interpretation": (
            "Direct linear power is intentionally included as a negative control; turbine power curves are nonlinear. "
            "Quadratic direct power is exploratory and must be revalidated across more years and target turbines before promotion."
        ),
    }
    Path(output_path).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(compare_methods(args.canonical, args.registry, args.output), indent=2))


if __name__ == "__main__":
    main()
