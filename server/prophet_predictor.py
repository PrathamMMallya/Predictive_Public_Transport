"""
Prophet forecasting — alternative to ARIMA (arima_predictor.py).

Prophet shines on data with strong daily seasonality (bus crowding has two
commute peaks per day). Fits are cached in memory for 10 minutes because a
Prophet fit takes a couple of seconds — the cached forecast is reused for
repeated asks on the same route.
"""

import time
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_CACHE = {}  # cache_key -> (expiry_ts, [int forecasts])
_CACHE_TTL = 600  # seconds


def predict_prophet(series_with_ts, steps, cache_key=None):
    """
    series_with_ts: [(datetime, oci), ...] hourly history.
    Returns `steps` non-negative int forecasts for the next hours.
    Falls back to the naive daily-pattern forecast if Prophet fails.
    """
    if cache_key and cache_key in _CACHE:
        expiry, cached = _CACHE[cache_key]
        if time.time() < expiry and len(cached) >= steps:
            return cached[:steps]

    values = [(ds, y) for ds, y in series_with_ts if y is not None]
    if len(values) < 12:
        return _naive([y for _, y in values], steps)

    try:
        from prophet import Prophet

        df = pd.DataFrame(values, columns=["ds", "y"])
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=False,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05,
            interval_width=0.8,
        )
        model.fit(df)
        future = model.make_future_dataframe(periods=steps, freq="h")
        forecast = model.predict(future)
        preds = np.clip(forecast["yhat"].tail(steps).to_numpy(), 0, 130)
        result = [int(round(v)) for v in preds]
    except Exception as e:
        print(f"Prophet failed ({e}) — naive fallback", flush=True)
        result = _naive([y for _, y in values], steps)

    if cache_key:
        _CACHE[cache_key] = (time.time() + _CACHE_TTL, result)
    return result


def _naive(values, steps):
    if not values:
        return [0] * steps
    if len(values) >= 12:
        pattern = values[-12:]
        return [int(pattern[i % len(pattern)]) for i in range(steps)]
    return [int(np.mean(values[-4:]))] * steps
