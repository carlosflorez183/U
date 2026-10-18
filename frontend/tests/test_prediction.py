"""Pruebas sintéticas reproducibles para los modelos predictivos."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from prediction import (
    PredictionConfig,
    PredictionValidationError,
    compare_models,
    fit_predict_linear,
    predict_knn,
    prepare_next_step,
    regression_metrics,
    samples_to_frame,
    temporal_holdout,
)


class PredictionTests(unittest.TestCase):
    def _samples(self, count: int = 40) -> list[dict[str, object]]:
        rng = np.random.default_rng(20250308)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        humidity = 60.0
        samples: list[dict[str, object]] = []
        for sequence in range(count):
            humidity = float(
                np.clip(
                    0.9 * humidity
                    + 0.08 * (20 + 5 * np.sin(sequence / 4))
                    + rng.normal(0, 0.15),
                    0,
                    100,
                )
            )
            temperature = float(22 + 3 * np.sin(sequence / 6) + rng.normal(0, 0.1))
            temperature = float(np.clip(temperature, -40, 80))
            samples.append(
                {
                    "id": f"sample-{sequence}",
                    "device_id": "esp32-01",
                    "sequence": sequence,
                    "measured_at": (start + timedelta(seconds=5 * sequence)).isoformat(),
                    "sampling_period_seconds": 5,
                    "ambient": {
                        "temperature_celsius": temperature,
                        "humidity_percent": humidity,
                    },
                    "quality_flags": ["synthetic"] if sequence == 3 else [],
                }
            )
        return samples

    def test_samples_to_frame_preserves_traceability_and_flags(self) -> None:
        frame = samples_to_frame(self._samples(5))
        self.assertEqual(
            {
                "id",
                "device",
                "sequence",
                "fecha",
                "sampling_period_seconds",
                "soil",
                "rain",
                "detected",
                "quality_flags",
            },
            set(frame.columns),
        )
        self.assertEqual(["synthetic"], frame.loc[3, "quality_flags"])
        self.assertEqual("UTC", str(frame.loc[0, "fecha"].tzinfo))

    def test_prepare_next_step_rejects_sequence_jump_and_large_gap(self) -> None:
        frame = samples_to_frame(self._samples(8))
        frame.loc[3, "sequence"] = 20
        frame.at[6, "fecha"] = pd.Timestamp(frame.at[5, "fecha"]) + pd.Timedelta(
            30, unit="s"
        )
        pairs = prepare_next_step(frame)
        sequences = set(pairs["sequence"].tolist())
        self.assertNotIn(2, sequences)
        self.assertNotIn(3, sequences)
        self.assertNotIn(5, sequences)
        self.assertTrue((pairs["target_sequence"] == pairs["sequence"] + 1).all())
        self.assertIn("target_quality_flags", pairs.columns)

    def test_temporal_holdout_purges_boundary_target(self) -> None:
        pairs = prepare_next_step(samples_to_frame(self._samples(30)))
        train, test = temporal_holdout(pairs)
        self.assertLess(train["target_time"].max(), test["fecha"].min())
        self.assertGreaterEqual(len(train), 10)
        self.assertGreaterEqual(len(test), 3)

    def test_linear_regression_recovers_exact_relation(self) -> None:
        train_x = np.arange(12, dtype=float).reshape(-1, 1)
        train_y = 2.0 + 3.0 * train_x[:, 0]
        test_x = np.array([[12.0], [13.0]])
        prediction, diagnostics = fit_predict_linear(train_x, train_y, test_x)
        np.testing.assert_allclose(prediction, [38.0, 41.0], atol=1e-10)
        self.assertTrue(diagnostics["well_conditioned"])
        self.assertEqual(0, diagnostics["clipped_predictions"])

    def test_linear_clipping_is_explicit(self) -> None:
        train_x = np.arange(10, dtype=float).reshape(-1, 1)
        train_y = train_x[:, 0] * 20
        prediction, diagnostics = fit_predict_linear(
            train_x, train_y, np.array([[20.0]])
        )
        self.assertEqual(100.0, prediction[0])
        self.assertEqual(1, diagnostics["clipped_predictions"])

    def test_knn_tie_is_stable_and_k_is_validated(self) -> None:
        train_x = np.array([[-1.0], [1.0]])
        train_y = np.array([10.0, 90.0])
        prediction = predict_knn(train_x, train_y, np.array([[0.0]]), k=1)
        self.assertEqual(10.0, prediction[0])
        with self.assertRaises(PredictionValidationError):
            predict_knn(train_x, train_y, np.array([[0.0]]), k=3)

    def test_metrics_have_expected_values(self) -> None:
        metrics = regression_metrics(
            np.array([1.0, 2.0, 3.0]), np.array([2.0, 2.0, 2.0])
        )
        self.assertAlmostEqual(2 / 3, metrics["mae"])
        self.assertAlmostEqual(np.sqrt(2 / 3), metrics["rmse"])
        self.assertAlmostEqual(0.0, metrics["r2"])
        self.assertAlmostEqual(0.0, metrics["bias"])

    def test_nan_and_insufficient_data_are_rejected(self) -> None:
        samples = self._samples(5)
        samples[2]["ambient"] = {
            "temperature_celsius": 22.0,
            "humidity_percent": float("nan"),
        }
        with self.assertRaises(PredictionValidationError):
            samples_to_frame(samples)
        with self.assertRaises(PredictionValidationError):
            compare_models(samples_to_frame(self._samples(10)))

    def test_comparison_is_deterministic_and_includes_baseline(self) -> None:
        frame = samples_to_frame(self._samples())
        first = compare_models(frame)
        second = compare_models(frame)
        pd.testing.assert_frame_equal(first.predictions, second.predictions)
        pd.testing.assert_frame_equal(first.metrics, second.metrics)
        self.assertEqual(
            ["Persistencia", "Regresión lineal", "k-NN (k=5)"],
            first.metrics["algorithm"].tolist(),
        )
        self.assertLess(
            first.diagnostics["train_target_end"], first.diagnostics["test_start"]
        )
        self.assertTrue(np.isfinite(first.predictions.select_dtypes("number")).all().all())

    def test_config_rejects_invalid_values(self) -> None:
        with self.assertRaises(PredictionValidationError):
            PredictionConfig(k_neighbors=0)
        with self.assertRaises(PredictionValidationError):
            PredictionConfig(clip_lower=100, clip_upper=0)


if __name__ == "__main__":
    unittest.main()
