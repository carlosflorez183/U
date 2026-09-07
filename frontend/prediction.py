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


# API experimental independiente para clasificar lluvia confirmada futura.
_RAIN_FEATURE_INVALID_FLAGS = frozenset(
    {"SOIL_ADC_RAIL", "TIMESTAMP_FUTURE", "STALE_SAMPLE"}
)
_RAIN_LABEL_INVALID_FLAGS = frozenset(
    {
        "RAIN_DETECTION_MISMATCH",
        "RAIN_ADC_RAIL",
        "TIMESTAMP_FUTURE",
        "STALE_SAMPLE",
    }
)


@dataclass(frozen=True, slots=True)
class RainPredictionConfig:
    """Configuración reproducible del clasificador experimental de lluvia."""

    horizon_minutes: int = 60
    lag_minutes: tuple[int, ...] = (15, 60, 180)
    lookback_minutes: int = 180
    threshold: float = 0.5
    train_fraction: float = 0.8
    min_train_samples: int = 20
    min_test_samples: int = 5
    l2_penalty: float = 1.0
    max_iterations: int = 100
    tolerance: float = 1.0e-7
    max_gap_factor: float = 3.0

    def __post_init__(self) -> None:
        if type(self.horizon_minutes) is not int or self.horizon_minutes <= 0:
            raise PredictionValidationError("horizon_minutes debe ser un entero positivo.")
        if (
            not isinstance(self.lag_minutes, tuple)
            or not self.lag_minutes
            or any(type(value) is not int or value <= 0 for value in self.lag_minutes)
            or tuple(sorted(set(self.lag_minutes))) != self.lag_minutes
        ):
            raise PredictionValidationError(
                "lag_minutes debe ser una tupla ordenada de enteros positivos únicos."
            )
        if type(self.lookback_minutes) is not int or self.lookback_minutes <= 0:
            raise PredictionValidationError("lookback_minutes debe ser un entero positivo.")
        if self.lookback_minutes < max(self.lag_minutes):
            raise PredictionValidationError(
                "lookback_minutes debe cubrir el mayor lag temporal."
            )
        if not math.isfinite(self.threshold) or not 0.0 <= self.threshold <= 1.0:
            raise PredictionValidationError("threshold debe estar entre 0 y 1.")
        if not math.isclose(self.train_fraction, 0.8, rel_tol=0.0, abs_tol=1.0e-12):
            raise PredictionValidationError("El backtest final exige train_fraction=0.8.")
        if type(self.min_train_samples) is not int or self.min_train_samples < 2:
            raise PredictionValidationError("min_train_samples debe ser un entero >= 2.")
        if type(self.min_test_samples) is not int or self.min_test_samples < 1:
            raise PredictionValidationError("min_test_samples debe ser un entero >= 1.")
        if not math.isfinite(self.l2_penalty) or self.l2_penalty <= 0:
            raise PredictionValidationError("l2_penalty debe ser finito y positivo.")
        if type(self.max_iterations) is not int or self.max_iterations < 1:
            raise PredictionValidationError("max_iterations debe ser un entero positivo.")
        if not math.isfinite(self.tolerance) or self.tolerance <= 0:
            raise PredictionValidationError("tolerance debe ser finita y positiva.")
        if not math.isfinite(self.max_gap_factor) or self.max_gap_factor < 1.0:
            raise PredictionValidationError("max_gap_factor debe ser finito y >= 1.")


@dataclass(frozen=True, slots=True)
class RainPredictionResult:
    """Backtest, métricas y pronóstico vigente del modelo experimental."""

    predictions: pd.DataFrame
    metrics: pd.DataFrame
    forecast_probability: float
    forecast_class: int
    forecast_time: pd.Timestamp
    forecast_horizon_end: pd.Timestamp
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SoilRainEstimate:
    """Estimación local basada en muestras históricas cercanas de humedad del suelo."""

    soil_percent: float
    probability: float
    predicted: bool
    threshold: float
    neighbors: pd.DataFrame
    valid_rows: int
    discarded_rows: int
    confirmed_rain_rows: int
    neighbor_rain_rows: int
    global_probability: float


@dataclass(frozen=True, slots=True)
class _RainLogisticModel:
    coefficients: np.ndarray
    mean: np.ndarray
    scale: np.ndarray
    prior_log_odds: float
    iterations: int
    converged: bool


def _rain_feature_names(config: RainPredictionConfig) -> tuple[str, ...]:
    names: list[str] = ["soil_current"]
    names.extend(f"soil_lag_{lag}m" for lag in config.lag_minutes)
    names.extend(f"soil_delta_{lag}m" for lag in config.lag_minutes)
    names.extend(("soil_window_mean", "soil_window_std", "soil_window_slope"))
    return tuple(names)


def _rain_flags(value: Any, row_number: int) -> frozenset[str]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(flag, str) for flag in value
    ):
        raise PredictionValidationError(
            f"quality_flags de la fila {row_number} debe ser una lista de textos."
        )
    return frozenset(value)


def _prepare_rain_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = _validate_model_frame(frame)
    devices = prepared["device"].drop_duplicates().tolist()
    if len(devices) != 1:
        raise PredictionValidationError(
            "predict_future_rain requiere exactamente un dispositivo concreto."
        )
    if prepared["fecha"].duplicated().any():
        raise PredictionValidationError(
            "Hay timestamps duplicados; no se puede reconstruir la cobertura temporal."
        )
    if not prepared["detected"].map(lambda value: type(value) is bool).all():
        raise PredictionValidationError("detected debe contener booleanos.")
    if not np.isfinite(prepared[["soil", "rain"]].to_numpy(dtype=float)).all():
        raise PredictionValidationError("soil y rain deben contener valores finitos.")
    prepared["_flags"] = [
        _rain_flags(value, index)
        for index, value in enumerate(prepared["quality_flags"].tolist())
    ]
    return prepared.sort_values("fecha").reset_index(drop=True)


def estimate_rain_from_soil(
    frame: pd.DataFrame,
    soil_percent: float,
    *,
    threshold: float = 0.5,
    max_neighbors: int = 201,
) -> SoilRainEstimate:
    """Estima lluvia por vecinos históricos cercanos al valor de humedad indicado.

    No exige continuidad temporal: utiliza únicamente las filas válidas del rango
    consultado. La probabilidad es una frecuencia local con suavizado de Laplace.
    """
    if isinstance(soil_percent, bool) or not isinstance(
        soil_percent, (int, float, np.integer, np.floating)
    ):
        raise PredictionValidationError("La humedad del suelo debe ser numérica.")
    soil_value = float(soil_percent)
    if not math.isfinite(soil_value) or not 0.0 <= soil_value <= 100.0:
        raise PredictionValidationError("La humedad del suelo debe estar entre 0 y 100.")
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise PredictionValidationError("threshold debe estar entre 0 y 1.")
    if type(max_neighbors) is not int or max_neighbors < 5:
        raise PredictionValidationError("max_neighbors debe ser un entero >= 5.")

    prepared = _validate_model_frame(frame)
    devices = prepared["device"].drop_duplicates().tolist()
    if len(devices) != 1:
        raise PredictionValidationError(
            "La estimación requiere exactamente un dispositivo concreto."
        )
    if not prepared["detected"].map(lambda value: type(value) is bool).all():
        raise PredictionValidationError("detected debe contener booleanos.")
    if not np.isfinite(prepared[["soil", "rain"]].to_numpy(dtype=float)).all():
        raise PredictionValidationError("soil y rain deben contener valores finitos.")

    flags = [
        _rain_flags(value, index)
        for index, value in enumerate(prepared["quality_flags"].tolist())
    ]
    valid_mask = np.asarray(
        [not bool(row_flags & _RAIN_LABEL_INVALID_FLAGS) for row_flags in flags],
        dtype=bool,
    )
    valid = prepared.loc[valid_mask].copy()
    discarded_rows = int(len(prepared) - len(valid))
    if len(valid) < 5:
        raise PredictionValidationError(
            "Se necesitan al menos 5 registros de calidad dentro del rango seleccionado."
        )

    valid["confirmed_rain"] = (
        valid["detected"].to_numpy(dtype=bool)
        & (valid["rain"].to_numpy(dtype=float) >= 10.0)
    )
    valid["soil_distance"] = (valid["soil"] - soil_value).abs()
    desired_neighbors = max(15, int(round(math.sqrt(len(valid)) * 3.0)))
    if desired_neighbors % 2 == 0:
        desired_neighbors += 1
    neighbor_count = min(len(valid), max_neighbors, desired_neighbors)
    neighbors = valid.sort_values(
        ["soil_distance", "fecha"], ascending=[True, False]
    ).head(neighbor_count).copy()

    neighbor_rain_rows = int(neighbors["confirmed_rain"].sum())
    confirmed_rain_rows = int(valid["confirmed_rain"].sum())
    probability = (neighbor_rain_rows + 1.0) / (neighbor_count + 2.0)
    global_probability = (confirmed_rain_rows + 1.0) / (len(valid) + 2.0)
    return SoilRainEstimate(
        soil_percent=soil_value,
        probability=float(probability),
        predicted=bool(probability >= threshold),
        threshold=float(threshold),
        neighbors=neighbors.reset_index(drop=True),
        valid_rows=int(len(valid)),
        discarded_rows=discarded_rows,
        confirmed_rain_rows=confirmed_rain_rows,
        neighbor_rain_rows=neighbor_rain_rows,
        global_probability=float(global_probability),
    )


def _reported_gap_tolerances_ns(
    prepared: pd.DataFrame,
    config: RainPredictionConfig,
) -> np.ndarray:
    """Convierte el periodo reportado por cada muestra en una tolerancia local."""
    periods = prepared["sampling_period_seconds"].to_numpy(dtype=float)
    tolerances = np.ceil(
        periods * config.max_gap_factor * 1_000_000_000.0
    ).astype(np.int64)
    if len(tolerances) < 2 or (tolerances <= 0).any():
        raise PredictionValidationError(
            "Se necesitan varios periodos de muestreo válidos para medir cobertura."
        )
    return tolerances


def _soil_features_at(
    endpoint: int,
    *,
    timestamps_ns: np.ndarray,
    soil: np.ndarray,
    feature_invalid: np.ndarray,
    gap_tolerances_ns: np.ndarray,
    config: RainPredictionConfig,
) -> tuple[np.ndarray | None, str | None]:
    endpoint_time = int(timestamps_ns[endpoint])
    window_ns = config.lookback_minutes * 60 * 1_000_000_000
    window_start = endpoint_time - window_ns
    start = int(np.searchsorted(timestamps_ns, window_start, side="left"))
    if endpoint - start + 1 < 3:
        return None, "feature_coverage"

    selected_times = timestamps_ns[start : endpoint + 1]
    selected_tolerances = gap_tolerances_ns[start : endpoint + 1]
    boundary_gaps = np.diff(
        np.concatenate(
            (
                np.asarray([window_start], dtype=np.int64),
                selected_times.astype(np.int64, copy=False),
            )
        )
    )
    pair_tolerances = np.concatenate(
        (
            selected_tolerances[:1],
            np.maximum(selected_tolerances[:-1], selected_tolerances[1:]),
        )
    )
    if (boundary_gaps > pair_tolerances).any():
        return None, "feature_coverage"
    if feature_invalid[start : endpoint + 1].any():
        return None, "feature_quality"

    selected_soil = soil[start : endpoint + 1]
    current = float(soil[endpoint])
    lag_values: list[float] = []
    for lag in config.lag_minutes:
        lag_time = endpoint_time - lag * 60 * 1_000_000_000
        right = int(np.searchsorted(selected_times, lag_time, side="left"))
        if right >= len(selected_times):
            lag_value = float(selected_soil[-1])
        elif int(selected_times[right]) == lag_time:
            lag_value = float(selected_soil[right])
        elif right == 0:
            if int(selected_times[0]) - lag_time > int(selected_tolerances[0]):
                return None, "feature_coverage"
            lag_value = float(selected_soil[0])
        else:
            left = right - 1
            interpolation_gap = int(selected_times[right] - selected_times[left])
            interpolation_tolerance = int(
                max(selected_tolerances[left], selected_tolerances[right])
            )
            if interpolation_gap > interpolation_tolerance:
                return None, "feature_coverage"
            fraction = (lag_time - int(selected_times[left])) / interpolation_gap
            lag_value = float(
                selected_soil[left]
                + fraction * (selected_soil[right] - selected_soil[left])
            )
        lag_values.append(lag_value)

    elapsed_minutes = (selected_times - endpoint_time).astype(float) / 60_000_000_000.0
    centered_time = elapsed_minutes - elapsed_minutes.mean()
    denominator = float(np.dot(centered_time, centered_time))
    if denominator <= 0:
        return None, "feature_coverage"
    centered_soil = selected_soil - selected_soil.mean()
    slope = float(np.dot(centered_time, centered_soil) / denominator)
    features = np.asarray(
        [
            current,
            *lag_values,
            *(current - value for value in lag_values),
            float(selected_soil.mean()),
            float(selected_soil.std(ddof=0)),
            slope,
        ],
        dtype=float,
    )
    if not np.isfinite(features).all():
        return None, "feature_non_finite"
    return features, None


def _build_rain_examples(
    prepared: pd.DataFrame,
    config: RainPredictionConfig,
) -> tuple[pd.DataFrame, np.ndarray, tuple[str, ...], dict[str, int], np.ndarray]:
    timestamps = prepared["fecha"]
    timestamps_ns = timestamps.astype("int64").to_numpy(dtype=np.int64)
    soil = prepared["soil"].to_numpy(dtype=float)
    rain = prepared["rain"].to_numpy(dtype=float)
    detected = prepared["detected"].to_numpy(dtype=bool)
    flags = prepared["_flags"].tolist()
    feature_invalid = np.asarray(
        [bool(row_flags & _RAIN_FEATURE_INVALID_FLAGS) for row_flags in flags],
        dtype=bool,
    )
    label_invalid = np.asarray(
        [bool(row_flags & _RAIN_LABEL_INVALID_FLAGS) for row_flags in flags],
        dtype=bool,
    )
    gap_tolerances_ns = _reported_gap_tolerances_ns(prepared, config)
    horizon_ns = config.horizon_minutes * 60 * 1_000_000_000
    lookback_ns = config.lookback_minutes * 60 * 1_000_000_000
    names = _rain_feature_names(config)
    rows: list[dict[str, Any]] = []
    feature_rows: list[np.ndarray] = []
    discarded = {
        "feature_coverage": 0,
        "feature_quality": 0,
        "feature_non_finite": 0,
        "label_coverage": 0,
        "label_quality": 0,
    }

    for endpoint in range(len(prepared)):
        features, reason = _soil_features_at(
            endpoint,
            timestamps_ns=timestamps_ns,
            soil=soil,
            feature_invalid=feature_invalid,
            gap_tolerances_ns=gap_tolerances_ns,
            config=config,
        )
        if features is None:
            discarded[reason or "feature_coverage"] += 1
            continue

        feature_time_ns = int(timestamps_ns[endpoint])
        label_end_ns = feature_time_ns + horizon_ns
        future_start = int(np.searchsorted(timestamps_ns, feature_time_ns, side="right"))
        future_end = int(np.searchsorted(timestamps_ns, label_end_ns, side="right"))
        if future_start >= future_end:
            discarded["label_coverage"] += 1
            continue
        future_times = timestamps_ns[future_start:future_end]
        coverage_gaps = np.diff(
            np.concatenate(
                (
                    np.asarray([feature_time_ns], dtype=np.int64),
                    future_times.astype(np.int64, copy=False),
                    np.asarray([label_end_ns], dtype=np.int64),
                )
            )
        )
        future_tolerances = gap_tolerances_ns[future_start:future_end]
        coverage_tolerances = np.concatenate(
            (
                np.asarray(
                    [
                        max(
                            gap_tolerances_ns[endpoint],
                            future_tolerances[0],
                        )
                    ],
                    dtype=np.int64,
                ),
                np.maximum(future_tolerances[:-1], future_tolerances[1:]),
                future_tolerances[-1:],
            )
        )
        if (coverage_gaps > coverage_tolerances).any():
            discarded["label_coverage"] += 1
            continue
        if label_invalid[future_start:future_end].any():
            discarded["label_quality"] += 1
            continue

        confirmed = detected[future_start:future_end] & (
            rain[future_start:future_end] >= 10.0
        )
        rows.append(
            {
                "feature_time": timestamps.iloc[endpoint],
                "feature_window_start": pd.Timestamp(
                    feature_time_ns - lookback_ns, tz="UTC"
                ),
                "label_end": pd.Timestamp(label_end_ns, tz="UTC"),
                "device": prepared["device"].iloc[endpoint],
                "sequence": int(prepared["sequence"].iloc[endpoint]),
                "actual": int(confirmed.any()),
            }
        )
        feature_rows.append(features)

    if not rows:
        raise PredictionValidationError(
            "No hay ejemplos con cobertura temporal y calidad suficientes."
        )
    return (
        pd.DataFrame(rows),
        np.vstack(feature_rows),
        names,
        discarded,
        gap_tolerances_ns,
    )


def _fit_rain_logistic(
    train_x: np.ndarray,
    train_y: np.ndarray,
    config: RainPredictionConfig,
) -> _RainLogisticModel:
    x = np.asarray(train_x, dtype=float)
    y = np.asarray(train_y, dtype=float)
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or len(x) < 2:
        raise PredictionValidationError("Los datos del clasificador no tienen forma válida.")
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise PredictionValidationError("El clasificador no admite NaN o infinito.")
    positive = int(np.count_nonzero(y == 1.0))
    negative = int(np.count_nonzero(y == 0.0))
    if positive == 0 or negative == 0 or positive + negative != len(y):
        raise PredictionValidationError(
            "El entrenamiento requiere ejemplos positivos y negativos confirmados."
        )

    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0.0] = 1.0
    design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    sample_weight = np.where(
        y == 1.0,
        len(y) / (2.0 * positive),
        len(y) / (2.0 * negative),
    )
    coefficients = np.zeros(design.shape[1], dtype=float)
    penalty = np.eye(design.shape[1], dtype=float)
    penalty[0, 0] = 0.0
    converged = False
    iterations = 0

    for iterations in range(1, config.max_iterations + 1):
        scores = np.clip(design @ coefficients, -35.0, 35.0)
        probability = 1.0 / (1.0 + np.exp(-scores))
        gradient = design.T @ (sample_weight * (probability - y))
        gradient += config.l2_penalty * (penalty @ coefficients)
        curvature = sample_weight * probability * (1.0 - probability)
        hessian = design.T @ (design * curvature[:, None])
        hessian += config.l2_penalty * penalty
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
        coefficients -= step
        if float(np.max(np.abs(step))) <= config.tolerance:
            converged = True
            break

    prior = positive / len(y)
    return _RainLogisticModel(
        coefficients=coefficients,
        mean=mean,
        scale=scale,
        prior_log_odds=float(math.log(prior / (1.0 - prior))),
        iterations=iterations,
        converged=converged,
    )


def _rain_probability(model: _RainLogisticModel, values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(model.mean):
        raise PredictionValidationError("Las features no coinciden con el modelo ajustado.")
    design = np.column_stack((np.ones(len(x)), (x - model.mean) / model.scale))
    scores = np.clip(
        design @ model.coefficients + model.prior_log_odds,
        -35.0,
        35.0,
    )
    return 1.0 / (1.0 + np.exp(-scores))


def _binary_metrics(
    actual: np.ndarray,
    probability: np.ndarray,
    threshold: float,
) -> dict[str, float | int | None]:
    y = np.asarray(actual, dtype=int)
    p = np.asarray(probability, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or len(y) == 0 or len(y) != len(p):
        raise PredictionValidationError("Los vectores de métricas no tienen tamaño válido.")
    predicted = (p >= threshold).astype(int)
    tp = int(np.count_nonzero((y == 1) & (predicted == 1)))
    tn = int(np.count_nonzero((y == 0) & (predicted == 0)))
    fp = int(np.count_nonzero((y == 0) & (predicted == 1)))
    fn = int(np.count_nonzero((y == 1) & (predicted == 0)))

    def ratio(numerator: float, denominator: float) -> float | None:
        return float(numerator / denominator) if denominator > 0 else None

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    specificity = ratio(tn, tn + fp)
    f1 = ratio(2 * tp, 2 * tp + fp + fn)
    balanced_accuracy = None
    if recall is not None and specificity is not None:
        balanced_accuracy = float((recall + specificity) / 2.0)

    positive = int(np.count_nonzero(y == 1))
    negative = int(np.count_nonzero(y == 0))
    roc_auc = None
    if positive and negative:
        ranks = pd.Series(p).rank(method="average").to_numpy(dtype=float)
        rank_sum = float(ranks[y == 1].sum())
        roc_auc = float(
            (rank_sum - positive * (positive + 1) / 2.0) / (positive * negative)
        )
    return {
        "accuracy": float(np.mean(predicted == y)),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": balanced_accuracy,
        "brier": float(np.mean((p - y) ** 2)),
        "roc_auc": roc_auc,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def predict_future_rain(
    frame: pd.DataFrame,
    config: RainPredictionConfig | None = None,
) -> RainPredictionResult:
    """Evalúa y reentrena lluvia futura usando únicamente historia de ``soil`` en X."""
    config = config or RainPredictionConfig()
    prepared = _prepare_rain_frame(frame)
    examples, feature_values, feature_names, discarded, gap_tolerances_ns = (
        _build_rain_examples(prepared, config)
    )
    minimum = config.min_train_samples + config.min_test_samples
    if len(examples) < minimum:
        raise PredictionValidationError(
            f"Se requieren al menos {minimum} ejemplos válidos; hay {len(examples)}."
        )
    total_positive = int(examples["actual"].sum())
    if total_positive == 0:
        raise PredictionValidationError("No hay eventos futuros de lluvia confirmada.")
    if total_positive == len(examples):
        raise PredictionValidationError("No hay ejemplos negativos sin lluvia confirmada.")

    cut = int(len(examples) * config.train_fraction)
    cut = min(cut, len(examples) - config.min_test_samples)
    if cut < 1:
        raise PredictionValidationError("No fue posible formar el holdout temporal 80/20.")
    test = examples.iloc[cut:].copy()
    test_start = test["feature_time"].min()
    train_mask = np.arange(len(examples)) < cut
    train_mask &= (examples["label_end"] < test_start).to_numpy()
    train_indices = np.flatnonzero(train_mask)
    test_indices = np.arange(cut, len(examples))
    purged_rows = int(cut - len(train_indices))
    if len(train_indices) < config.min_train_samples:
        raise PredictionValidationError(
            "La purga temporal dejó pocas muestras de entrenamiento; amplíe el histórico."
        )
    if len(test_indices) < config.min_test_samples:
        raise PredictionValidationError("Hay pocas muestras en el 20% de evaluación.")

    train_y = examples.iloc[train_indices]["actual"].to_numpy(dtype=int)
    test_y = examples.iloc[test_indices]["actual"].to_numpy(dtype=int)
    train_positive = int(train_y.sum())
    test_positive = int(test_y.sum())
    if train_positive == 0 or train_positive == len(train_y):
        raise PredictionValidationError(
            "El entrenamiento purgado requiere clases positiva y negativa; amplíe el histórico."
        )
    if test_positive == 0 or test_positive == len(test_y):
        raise PredictionValidationError(
            "El bloque final de prueba requiere clases positiva y negativa para evaluar; "
            "amplíe el histórico."
        )

    backtest_model = _fit_rain_logistic(
        feature_values[train_indices], train_y, config
    )
    test_probability = _rain_probability(
        backtest_model, feature_values[test_indices]
    )
    train_prevalence = float(train_y.mean())
    baseline_probability = np.full(len(test_indices), train_prevalence, dtype=float)
    model_metrics = _binary_metrics(test_y, test_probability, config.threshold)
    baseline_metrics = _binary_metrics(test_y, baseline_probability, config.threshold)
    metrics = pd.DataFrame(
        [
            {"algorithm": "Regresión logística L2", **model_metrics},
            {"algorithm": "Baseline prevalencia", **baseline_metrics},
        ]
    )

    predictions = test.reset_index(drop=True)
    predictions["probability"] = test_probability
    predictions["predicted"] = (test_probability >= config.threshold).astype(int)
    predictions["baseline_probability"] = baseline_probability
    predictions["baseline_predicted"] = (
        baseline_probability >= config.threshold
    ).astype(int)

    full_y = examples["actual"].to_numpy(dtype=int)
    final_model = _fit_rain_logistic(feature_values, full_y, config)
    timestamps_ns = prepared["fecha"].astype("int64").to_numpy(dtype=np.int64)
    latest_features, latest_reason = _soil_features_at(
        len(prepared) - 1,
        timestamps_ns=timestamps_ns,
        soil=prepared["soil"].to_numpy(dtype=float),
        feature_invalid=np.asarray(
            [
                bool(row_flags & _RAIN_FEATURE_INVALID_FLAGS)
                for row_flags in prepared["_flags"].tolist()
            ],
            dtype=bool,
        ),
        gap_tolerances_ns=gap_tolerances_ns,
        config=config,
    )
    if latest_features is None:
        reason_text = {
            "feature_quality": "la ventana vigente contiene flags que invalidan soil",
            "feature_coverage": "la ventana vigente no tiene cobertura temporal suficiente",
            "feature_non_finite": "la ventana vigente contiene valores no finitos",
        }.get(latest_reason, "la ventana vigente no es válida")
        raise PredictionValidationError(f"No se puede generar el pronóstico: {reason_text}.")
    forecast_probability = float(
        _rain_probability(final_model, latest_features.reshape(1, -1))[0]
    )
    forecast_time = pd.Timestamp(prepared["fecha"].iloc[-1])
    forecast_horizon_end = forecast_time + pd.Timedelta(
        minutes=config.horizon_minutes
    )
    evaluated_at = pd.Timestamp.now(tz="UTC")
    forecast_age_seconds = float((evaluated_at - forecast_time).total_seconds())
    forecast_is_current = bool(
        forecast_time <= evaluated_at + pd.Timedelta(minutes=2)
        and forecast_horizon_end > evaluated_at
    )
    label_quality_valid = np.asarray(
        [
            not bool(row_flags & _RAIN_LABEL_INVALID_FLAGS)
            for row_flags in prepared["_flags"].tolist()
        ],
        dtype=bool,
    )
    confirmed_history = (
        prepared["detected"].to_numpy(dtype=bool)
        & (prepared["rain"].to_numpy(dtype=float) >= 10.0)
        & label_quality_valid
    )
    episode_starts = confirmed_history & ~np.concatenate(
        (np.asarray([False]), confirmed_history[:-1])
    )

    diagnostics: dict[str, Any] = {
        "device": str(prepared["device"].iloc[0]),
        "raw_rows": int(len(prepared)),
        "valid_examples": int(len(examples)),
        "train_size": int(len(train_indices)),
        "test_size": int(len(test_indices)),
        "train_positives": train_positive,
        "test_positives": test_positive,
        "all_positives": total_positive,
        "train_prevalence": train_prevalence,
        "test_prevalence": float(test_y.mean()),
        "all_prevalence": float(full_y.mean()),
        "purged_rows": purged_rows,
        "discarded_rows": int(sum(discarded.values())),
        "discarded_by_reason": discarded,
        "horizon_minutes": config.horizon_minutes,
        "lookback_minutes": config.lookback_minutes,
        "lag_minutes": config.lag_minutes,
        "features": feature_names,
        "threshold": config.threshold,
        "confirmed_episode_starts": int(np.count_nonzero(episode_starts)),
        "forecast_is_current": forecast_is_current,
        "forecast_age_seconds": forecast_age_seconds,
        "evaluated_at": evaluated_at,
        "max_gap_seconds": float(gap_tolerances_ns.max() / 1_000_000_000.0),
        "test_feature_time_start": test_start,
        "train_label_end": examples.iloc[train_indices]["label_end"].max(),
        "backtest_iterations": backtest_model.iterations,
        "backtest_converged": backtest_model.converged,
        "final_iterations": final_model.iterations,
        "final_converged": final_model.converged,
    }
    return RainPredictionResult(
        predictions=predictions,
        metrics=metrics,
        forecast_probability=forecast_probability,
        forecast_class=int(forecast_probability >= config.threshold),
        forecast_time=forecast_time,
        forecast_horizon_end=forecast_horizon_end,
        diagnostics=diagnostics,
    )
