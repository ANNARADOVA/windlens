"""Run wind-first and direct-power comparisons across all Hill turbines."""

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
    pred_energy = integrate_energy_kwh(predicted)
    actual_energy = integrate_energy_kwh(actual)
    return {
        "rmse_kw": float(np.sqrt(np.mean((predicted - actual) ** 2))),
        "mae_kw": float(np.mean(np.abs(predicted - actual))),
        "expected_kwh": pred_energy,
        "actual_kwh": actual_energy,
        "relative_energy_error_pct": float(abs(pred_energy - actual_energy) / max(actual_energy, 1e-9) * 100),
    }


def run_sweep(
    canonical_path: str | Path,
    registry_path: str | Path,
    output_path: str | Path,
    *,
    blocks: tuple[tuple[str, str], ...] = BLOCKS,
) -> dict:
    data = pd.read_csv(canonical_path)
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    metadata = pd.read_csv(registry_path)
    targets = sorted(data["turbine_id"].unique())
    records = []
    for target in targets:
        candidates = [turbine for turbine in targets if turbine != target]
        for block_start, block_end in blocks:
            block_start_ts = pd.Timestamp(block_start, tz="UTC")
            pre = data[
                (data["timestamp_utc"] < block_start_ts)
                & (data["timestamp_utc"] >= block_start_ts - pd.Timedelta(days=180))
            ]
            selection = select_dynamic_references(
                pre, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3
            )
            if selection["status"] == "abstain":
                records.append({"target_turbine": target, "block_start": block_start, "status": "abstain", "reason": selection["reason"]})
                continue
            reference = selection["selected"]
            truth = data[(data["turbine_id"] == target) & (data["timestamp_utc"] >= block_start) & (data["timestamp_utc"] < block_end)].sort_values("timestamp_utc")
            ref_event = data[(data["turbine_id"] == reference) & (data["timestamp_utc"] >= block_start) & (data["timestamp_utc"] < block_end)][["timestamp_utc", "active_power_kw"]]
            event = truth[["timestamp_utc", "active_power_kw"]].merge(ref_event, on="timestamp_utc", suffixes=("_target", "_reference")).dropna()
            if len(event) < 20:
                records.append({
                    "target_turbine": target,
                    "block_start": block_start,
                    "block_end": block_end,
                    "status": "unscorable",
                    "reason": f"only {len(event)} overlapping target/reference rows in held-out block",
                    "reference": reference,
                })
                continue
            train = pre[pre["turbine_id"].isin([target, reference])][["timestamp_utc", "turbine_id", "active_power_kw"]].pivot(index="timestamp_utc", columns="turbine_id", values="active_power_kw").dropna().rename(columns={target: "target", reference: "reference"})
            linear = np.polyfit(train["reference"], train["target"], 1)
            direct_power = np.clip(np.polyval(linear, event["active_power_kw_reference"]), 0, float(metadata.loc[metadata.turbine_id == target, "rated_power_kw"].iloc[0]))
            masked = data[~((data["turbine_id"] == target) & (data["timestamp_utc"] >= block_start) & (data["timestamp_utc"] < block_end))]
            reconstruction = reconstruct_wind_speed(masked, target, reference, block_start, block_end)
            curve = fit_power_curve(pre[pre["turbine_id"] == target])
            wind_frame = reconstruction[["timestamp_utc"]].copy()
            wind_frame["predicted_power_kw"] = apply_power_curve(curve, reconstruction["wind_speed_ms_reconstructed"].to_numpy())
            wind_event = wind_frame.merge(truth[["timestamp_utc", "active_power_kw"]], on="timestamp_utc").dropna()
            records.append({
                "target_turbine": target,
                "block_start": block_start,
                "block_end": block_end,
                "status": "scored",
                "reference": reference,
                "selected_window_days": selection["selected_window_days"],
                "direct_power": _metrics(direct_power, event["active_power_kw_target"].to_numpy()),
                "wind_first": _metrics(wind_event["predicted_power_kw"].to_numpy(), wind_event["active_power_kw"].to_numpy()),
            })
    scored = [record for record in records if record["status"] == "scored"]
    aggregate = {}
    for method in ("direct_power", "wind_first"):
        total_actual = sum(record[method]["actual_kwh"] for record in scored)
        total_abs_error = sum(abs(record[method]["expected_kwh"] - record[method]["actual_kwh"]) for record in scored)
        total_bias = sum(record[method]["expected_kwh"] - record[method]["actual_kwh"] for record in scored)
        aggregate[method] = {
            "energy_weighted_wape_pct": total_abs_error / max(total_actual, 1e-9) * 100,
            "signed_aggregate_bias_pct": total_bias / max(total_actual, 1e-9) * 100,
        }
    artifact = {
        "artifact_version": "method-sweep.v1",
        "farm_id": "Hill of Towie",
        "canonical_path": str(canonical_path),
        "canonical_md5": file_md5(Path(canonical_path)),
        "registry_path": str(registry_path),
        "registry_md5": file_md5(Path(registry_path)),
        "target_count": len(targets),
        "block_count": len(blocks),
        "scored_event_count": len(scored),
        "unscorable_event_count": len(records) - len(scored),
        "abstention_count": sum(record.get("status") == "abstain" for record in records),
        "blocks": records,
        "aggregate": aggregate,
        "kelmarsh_training_used": False,
        "model_training_mixed_with_kelmarsh": False,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run_sweep(args.canonical, args.registry, args.output), indent=2))


if __name__ == "__main__":
    main()
