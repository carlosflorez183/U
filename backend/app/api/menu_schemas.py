"""DTOs de respuesta del menú del teclado matricial."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TrendLabel = Literal["SUBIENDO", "BAJANDO", "ESTABLE", "SIN_DATOS"]


class RealtimeReading(BaseModel):
    device_id: str
    group_id: str
    measured_at: datetime
    temperature_celsius: float | None
    humidity_percent: float | None
    temp_status: str | None
    humidity_status: str | None


class HourlyAverage(BaseModel):
    sample_count: int
    avg_temperature_celsius: float | None
    avg_humidity_percent: float | None


class DailyExtremes(BaseModel):
    sample_count: int
    min_temperature_celsius: float | None
    max_temperature_celsius: float | None
    min_humidity_percent: float | None
    max_humidity_percent: float | None


class TrendReport(BaseModel):
    sample_count: int
    temperature_now: float | None
    temperature_previous_hour: float | None
    humidity_now: float | None
    humidity_previous_hour: float | None
    stddev_temperature_celsius: float | None
    stddev_humidity_percent: float | None
    temperature_trend: TrendLabel
    humidity_trend: TrendLabel


class OutlierReport(BaseModel):
    outlier_count: int
    temperature_outlier_count: int
    humidity_outlier_count: int


class AlertReport(BaseModel):
    alert_count: int
    temperature_alert_count: int
    humidity_alert_count: int
    quality_alert_count: int


class DeviceConnectionStatus(BaseModel):
    device_id: str
    group_id: str
    device_name: str | None
    last_seen_at: datetime | None
    online: bool
