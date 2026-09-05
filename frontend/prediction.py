"""Preparación, entrenamiento y evaluación reproducible de modelos de humedad.

Este módulo no depende de Streamlit ni de red. Las funciones reciben datos en
memoria, validan sus invariantes y permiten pruebas sintéticas deterministas.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

_FEATURE_COLUMNS = ("soil", "rain", "detected")
_REQUIRED_FRAME_COLUMNS = {
    "id",
    "device",
    "sequence",
    "fecha",
    "sampling_period_seconds",
    "soil",
    "rain",
    "detected",
    "quality_flags",
}


class PredictionValidationError(ValueError):
    """Error controlado para datos o configuración no aptos para modelar."""


@dataclass(frozen=True, slots=True)
class PredictionConfig:
    """Parámetros explícitos de preparación y comparación temporal."""

    train_fraction: float = 0.8
    min_train_samples: int = 10
    min_test_samples: int = 3
    k_neighbors: int = 5
    max_gap_factor: float = 1.5
    clip_lower: float = 0.0
    clip_upper: float = 100.0
    max_condition_number: float = 1.0e10

    def __post_init__(self) -> None:
        if not 0.5 <= self.train_fraction < 1.0:
            raise PredictionValidationError("train_fraction debe estar entre 0.5 y 1.")
        if type(self.min_train_samples) is not int or self.min_train_samples < 2:
            raise PredictionValidationError("min_train_samples debe ser un entero >= 2.")
        if type(self.min_test_samples) is not int or self.min_test_samples < 1:
            raise PredictionValidationError("min_test_samples debe ser un entero >= 1.")
        if type(self.k_neighbors) is not int or self.k_neighbors < 1:
            raise PredictionValidationError("k_neighbors debe ser un entero positivo.")
        if not math.isfinite(self.max_gap_factor) or self.max_gap_factor < 1.0:
            raise PredictionValidationError("max_gap_factor debe ser finito y >= 1.")
        if not (
            math.isfinite(self.clip_lower)
            and math.isfinite(self.clip_upper)
            and self.clip_lower < self.clip_upper
        ):
            raise PredictionValidationError("Los límites de clipping no son válidos.")
        if not math.isfinite(self.max_condition_number) or self.max_condition_number <= 1:
            raise PredictionValidationError("max_condition_number debe ser finito y > 1.")


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Resultados listos para presentar o exportar."""

    predictions: pd.DataFrame
    metrics: pd.DataFrame
    diagnostics: dict[str, Any]


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise PredictionValidationError(f"{field} debe ser numérico.")
    result = float(value)
    if not math.isfinite(result):
        raise PredictionValidationError(f"{field} debe ser finito.")
    return result


def _strict_integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise PredictionValidationError(f"{field} debe ser un entero.")
    result = int(value)
    if result < minimum:
        raise PredictionValidationError(f"{field} debe ser >= {minimum}.")
    return result


def samples_to_frame(samples: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Convierte la respuesta v2 en una tabla tipada sin perder trazabilidad."""
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence):
        raise PredictionValidationError("Las muestras deben ser una secuencia JSON.")
    if not samples:
        raise PredictionValidationError("No hay muestras para preparar.")

    rows: list[dict[str, Any]] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            raise PredictionValidationError(f"La muestra {index} no es un objeto.")
        try:
            sample_id = sample["id"]
            device = sample["device_id"]
            sequence = _strict_integer(sample["sequence"], f"samples[{index}].sequence")
            sampling_period = _strict_integer(
                sample["sampling_period_seconds"],
                f"samples[{index}].sampling_period_seconds",
                minimum=1,
            )
            soil_payload = sample["soil_moisture"]
            rain_payload = sample["rain"]
            quality_flags = sample.get("quality_flags", [])
            measured_at = sample["measured_at"]
        except KeyError as exc:
            raise PredictionValidationError(
                f"La muestra {index} no contiene el campo {exc.args[0]}."
            ) from exc

        if not isinstance(sample_id, str) or not sample_id:
            raise PredictionValidationError(f"samples[{index}].id no es válido.")
        if not isinstance(device, str) or not device:
            raise PredictionValidationError(f"samples[{index}].device_id no es válido.")
        if not isinstance(soil_payload, Mapping) or not isinstance(rain_payload, Mapping):
            raise PredictionValidationError(
                f"La muestra {index} no contiene lecturas de sensor válidas."
            )
        detected = rain_payload.get("detected")
        if type(detected) is not bool:
            raise PredictionValidationError(
                f"samples[{index}].rain.detected debe ser booleano."
            )
        if not isinstance(quality_flags, list) or not all(
            isinstance(flag, str) for flag in quality_flags
        ):
            raise PredictionValidationError(
                f"samples[{index}].quality_flags debe ser una lista de textos."
            )

        parsed_date = pd.to_datetime(measured_at, utc=True, errors="coerce")
        if pd.isna(parsed_date):
            raise PredictionValidationError(f"samples[{index}].measured_at no es válido.")

        rows.append(
            {
                "id": sample_id,
                "device": device,
                "sequence": sequence,
                "fecha": parsed_date,
                "sampling_period_seconds": sampling_period,
                "soil": _finite_number(
                    soil_payload.get("percent"),
                    f"samples[{index}].soil_moisture.percent",
                ),
                "rain": _finite_number(
                    rain_payload.get("wetness_percent"),
                    f"samples[{index}].rain.wetness_percent",
                ),
                "detected": detected,
                "quality_flags": list(quality_flags),
            }
        )

    frame = pd.DataFrame(rows).drop_duplicates(subset=["id"], keep="last")
    if frame.duplicated(subset=["device", "sequence"]).any():
        raise PredictionValidationError(
            "Hay secuencias duplicadas para un mismo dispositivo."
        )
    return frame.sort_values(["fecha", "device", "sequence"]).reset_index(drop=True)


def _validate_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise PredictionValidationError("Se esperaba un DataFrame de muestras.")
    missing = sorted(_REQUIRED_FRAME_COLUMNS - set(frame.columns))
    if missing:
        raise PredictionValidationError("Faltan columnas: " + ", ".join(missing))
    if frame.empty:
        raise PredictionValidationError("No hay muestras para formar pares.")

    prepared = frame.copy()
    prepared["fecha"] = pd.to_datetime(prepared["fecha"], utc=True, errors="coerce")
    if prepared["fecha"].isna().any():
        raise PredictionValidationError("fecha contiene valores inválidos.")
    for column in ("sequence", "sampling_period_seconds"):
        if prepared[column].map(
            lambda value: isinstance(value, bool)
            or not isinstance(value, (int, np.integer))
        ).any():
            raise PredictionValidationError(f"{column} debe contener enteros.")
    numeric = prepared[list(_FEATURE_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise PredictionValidationError("Las variables predictoras contienen NaN o infinito.")
    if (prepared["sampling_period_seconds"] <= 0).any():
        raise PredictionValidationError("sampling_period_seconds debe ser positivo.")
    return prepared.sort_values(["device", "fecha", "sequence"]).reset_index(drop=True)


def prepare_next_step(
    frame: pd.DataFrame,
    config: PredictionConfig | None = None,
) -> pd.DataFrame:
    """Forma objetivos t+1 solo con secuencia y tiempo realmente continuos."""
    config = config or PredictionConfig()
    prepared = _validate_model_frame(frame)
    grouped = prepared.groupby("device", sort=False)
    prepared["target_sequence"] = grouped["sequence"].shift(-1)
    prepared["target_time"] = grouped["fecha"].shift(-1)
    prepared["target"] = grouped["soil"].shift(-1)
    prepared["target_sampling_period_seconds"] = grouped[
        "sampling_period_seconds"
    ].shift(-1)
    prepared["target_quality_flags"] = grouped["quality_flags"].shift(-1)

    prepared["gap_seconds"] = (
        prepared["target_time"] - prepared["fecha"]
    ).dt.total_seconds()
    expected_period = prepared[
        ["sampling_period_seconds", "target_sampling_period_seconds"]
    ].max(axis=1)
    valid = (
        prepared["target_sequence"].eq(prepared["sequence"] + 1)
        & prepared["target_time"].gt(prepared["fecha"])
        & prepared["gap_seconds"].le(expected_period * config.max_gap_factor)
    )
    pairs = prepared.loc[valid].copy()
    if pairs.empty:
        raise PredictionValidationError(
            "No existen pares consecutivos dentro del intervalo temporal permitido."
        )
    pairs["target_sequence"] = pairs["target_sequence"].astype("int64")
    return pairs.sort_values(["fecha", "device", "sequence"]).reset_index(drop=True)


def temporal_holdout(
    pairs: pd.DataFrame,
    config: PredictionConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide 80/20 y purga objetivos de entrenamiento que cruzan la frontera."""
    config = config or PredictionConfig()
    required = {"fecha", "target_time", "target"}
    missing = sorted(required - set(pairs.columns))
    if missing:
        raise PredictionValidationError("Faltan columnas de pares: " + ", ".join(missing))
    ordered = pairs.sort_values(["fecha", "device", "sequence"]).reset_index(drop=True)
    minimum_total = config.min_train_samples + config.min_test_samples + 1
    if len(ordered) < minimum_total:
        raise PredictionValidationError(
            f"Se requieren al menos {minimum_total} pares consecutivos."
        )

    cut = int(len(ordered) * config.train_fraction)
    cut = min(cut, len(ordered) - config.min_test_samples)
    if cut <= 0:
        raise PredictionValidationError("No fue posible crear la partición temporal.")
    test = ordered.iloc[cut:].copy()
    test_start = test["fecha"].min()
    train_before_purge = ordered.iloc[:cut]
    train = train_before_purge.loc[
        train_before_purge["target_time"] < test_start
    ].copy()

    if len(train) < config.min_train_samples:
        raise PredictionValidationError(
            "La purga temporal dejó pocas muestras de entrenamiento."
        )
    if len(test) < config.min_test_samples:
        raise PredictionValidationError("Hay pocas muestras de evaluación.")
    if not train["target_time"].max() < test["fecha"].min():
        raise PredictionValidationError("La partición conserva fuga temporal.")
    return train.reset_index(drop=True), test.reset_index(drop=True)


def _validated_arrays(
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_train = np.asarray(train_x, dtype=float)
    y_train = np.asarray(train_y, dtype=float)
    x_test = np.asarray(test_x, dtype=float)
    if x_train.ndim != 2 or x_test.ndim != 2:
        raise PredictionValidationError("Las matrices predictoras deben tener dos dimensiones.")
    if y_train.ndim != 1:
        raise PredictionValidationError("El objetivo debe tener una dimensión.")
    if len(x_train) != len(y_train) or len(x_train) < 2:
        raise PredictionValidationError("Entrenamiento y objetivo no tienen tamaños válidos.")
    if x_train.shape[1] == 0 or x_train.shape[1] != x_test.shape[1]:
        raise PredictionValidationError("Las matrices no tienen las mismas variables.")
    if len(x_test) == 0:
        raise PredictionValidationError("No hay filas para predecir.")
    if not (
        np.isfinite(x_train).all()
        and np.isfinite(y_train).all()
        and np.isfinite(x_test).all()
    ):
        raise PredictionValidationError("El modelo no admite NaN o infinito.")
    return x_train, y_train, x_test


def fit_predict_linear(
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
    *,
    clip_bounds: tuple[float, float] = (0.0, 100.0),
    max_condition_number: float = 1.0e10,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Ajusta mínimos cuadrados estandarizados y reporta estabilidad numérica."""
    x_train, y_train, x_test = _validated_arrays(train_x, train_y, test_x)
    lower, upper = clip_bounds
    if not (math.isfinite(lower) and math.isfinite(upper) and lower < upper):
        raise PredictionValidationError("Los límites de clipping no son válidos.")

    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale == 0] = 1.0
    train_design = np.column_stack([np.ones(len(x_train)), (x_train - mean) / scale])
    test_design = np.column_stack([np.ones(len(x_test)), (x_test - mean) / scale])
    rank = int(np.linalg.matrix_rank(train_design))
    condition = float(np.linalg.cond(train_design))
    weights = np.linalg.lstsq(train_design, y_train, rcond=None)[0]
    raw_prediction = test_design @ weights
    prediction = np.clip(raw_prediction, lower, upper)
    diagnostics = {
        "rank": rank,
        "columns": int(train_design.shape[1]),
        "condition_number": condition if math.isfinite(condition) else None,
        "well_conditioned": bool(
            rank == train_design.shape[1]
            and math.isfinite(condition)
            and condition <= max_condition_number
        ),
        "clipped_predictions": int(np.count_nonzero(raw_prediction != prediction)),
    }
    return prediction, diagnostics


def predict_knn(
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
    *,
    k: int,
    clip_bounds: tuple[float, float] = (0.0, 100.0),
) -> np.ndarray:
    """Predice k-NN estandarizado con desempate estable por orden temporal."""
    x_train, y_train, x_test = _validated_arrays(train_x, train_y, test_x)
    if type(k) is not int or not 1 <= k <= len(x_train):
        raise PredictionValidationError(
            "k debe ser entero y no superar las muestras de entrenamiento."
        )
    lower, upper = clip_bounds
    if not (math.isfinite(lower) and math.isfinite(upper) and lower < upper):
        raise PredictionValidationError("Los límites de clipping no son válidos.")

    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale == 0] = 1.0
    train_scaled = (x_train - mean) / scale
    test_scaled = (x_test - mean) / scale
    predictions: list[float] = []
    for row in test_scaled:
        distances = np.sum((train_scaled - row) ** 2, axis=1)
        neighbours = np.argsort(distances, kind="stable")[:k]
        predictions.append(float(np.mean(y_train[neighbours])))
    return np.clip(np.asarray(predictions), lower, upper)


def regression_metrics(
    actual: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float | None]:
    """Calcula MAE, RMSE, R² y sesgo con dimensiones y finitud comprobadas."""
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(prediction, dtype=float)
    if actual_values.ndim != 1 or predicted_values.ndim != 1:
        raise PredictionValidationError("Métricas requiere vectores de una dimensión.")
    if len(actual_values) == 0 or len(actual_values) != len(predicted_values):
        raise PredictionValidationError("Los vectores de métricas no tienen igual tamaño.")
    if not (np.isfinite(actual_values).all() and np.isfinite(predicted_values).all()):
        raise PredictionValidationError("Las métricas no admiten NaN o infinito.")

    errors = predicted_values - actual_values
    denominator = float(np.sum((actual_values - actual_values.mean()) ** 2))
    r_squared = None
    if denominator > 0:
        r_squared = float(1.0 - np.sum(errors**2) / denominator)
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "r2": r_squared,
        "bias": float(np.mean(errors)),
    }


def compare_models(
    frame: pd.DataFrame,
    config: PredictionConfig | None = None,
) -> PredictionResult:
    """Ejecuta preparación, holdout purgado, baseline, lineal y k-NN."""
    config = config or PredictionConfig()
    pairs = prepare_next_step(frame, config)
    train, test = temporal_holdout(pairs, config)
    if config.k_neighbors > len(train):
        raise PredictionValidationError(
            "k_neighbors supera las muestras disponibles de entrenamiento."
        )

    train_x = train[list(_FEATURE_COLUMNS)].to_numpy(dtype=float)
    train_y = train["target"].to_numpy(dtype=float)
    test_x = test[list(_FEATURE_COLUMNS)].to_numpy(dtype=float)
    actual = test["target"].to_numpy(dtype=float)
    clip_bounds = (config.clip_lower, config.clip_upper)

    persistence = np.clip(test["soil"].to_numpy(dtype=float), *clip_bounds)
    linear, linear_diagnostics = fit_predict_linear(
        train_x,
        train_y,
        test_x,
        clip_bounds=clip_bounds,
        max_condition_number=config.max_condition_number,
    )
    knn = predict_knn(
        train_x,
        train_y,
        test_x,
        k=config.k_neighbors,
        clip_bounds=clip_bounds,
    )

    metric_rows: list[dict[str, Any]] = []
    for algorithm, values in (
        ("Persistencia", persistence),
        ("Regresión lineal", linear),
        (f"k-NN (k={config.k_neighbors})", knn),
    ):
        metric_rows.append(
            {"algorithm": algorithm, **regression_metrics(actual, values)}
        )

    predictions = pd.DataFrame(
        {
            "fecha": test["fecha"].to_numpy(),
            "target_time": test["target_time"].to_numpy(),
            "device": test["device"].to_numpy(),
            "sequence": test["sequence"].to_numpy(),
            "target_sequence": test["target_sequence"].to_numpy(),
            "actual": actual,
            "persistence": persistence,
            "linear_regression": linear,
            "knn": knn,
        }
    )
    diagnostics = {
        "pair_count": len(pairs),
        "train_size": len(train),
        "test_size": len(test),
        "purged_rows": int(len(pairs) - len(train) - len(test)),
        "test_start": test["fecha"].min(),
        "train_target_end": train["target_time"].max(),
        "max_gap_factor": config.max_gap_factor,
        "linear": linear_diagnostics,
    }
    return PredictionResult(
        predictions=predictions,
        metrics=pd.DataFrame(metric_rows),
        diagnostics=diagnostics,
    )
