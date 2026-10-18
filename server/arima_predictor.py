"""
ARIMA forecasting utilities.

Design notes
------------
* Pure functions — no MongoDB / disk side effects (the old version silently
  connected to a *different* database and dumped a .pkl per request).
* The old version used order=(n-1, 1, n-1) — for 13 points that is
  ARIMA(12,1,12): massively over-parameterised, slow, and usually fails to
  converge. Here we do a small grid search over sensible orders and pick the
  best AIC, with graceful fallbacks when data is short or fits fail.
"""

import warnings

import numpy as np
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore")

# Sensible ARIMA orders for hourly crowding data, tried in order of preference.
_CANDIDATE_ORDERS = [(2, 1, 1), (1, 1, 1), (2, 1, 0), (0, 1, 1), (1, 0, 1), (0, 0, 0)]

_MIN_POINTS = 6  # below this, ARIMA is meaningless — use naive fallbacks


def _clean(values):
    """Coerce to a float numpy array, dropping None/NaN, clipping negatives."""
    arr = np.array(
        [float(v) for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))],
        dtype=float,
    )
    return np.clip(arr, 0, None)


def _fit_best_arima(series):
    """Grid-search small ARIMA orders, return the fit with the best AIC (or None)."""
    best_fit = None
    for order in _CANDIDATE_ORDERS:
        # AR/MA orders must stay well below the number of observations
        if order[0] + order[2] >= len(series) - 1:
            continue
        try:
            fit = ARIMA(series, order=order).fit()
            if np.isfinite(fit.aic) and (best_fit is None or fit.aic < best_fit.aic):
                best_fit = fit
        except Exception:
            continue
    return best_fit


def _naive_forecast(series, steps):
    """Fallback: repeat the last observed daily pattern, else the trailing mean."""
    if len(series) == 0:
        return [0] * steps
    if len(series) >= 12:
        # Repeat the last 12 hours as the expected daily rhythm, offset by steps
        pattern = series[-12:]
        return [float(pattern[i % len(pattern)]) for i in range(steps)]
    mean_val = float(np.mean(series[-4:]))
    return [mean_val] * steps


def predict_full_day(values, steps=None):
    """
    Forecast `steps` future points from an hourly series of crowding values.
    Returns a list of non-negative ints. Never raises on bad input.
    """
    series = _clean(values)
    if steps is None:
        steps = len(series)
    if steps <= 0:
        return []

    if len(series) < _MIN_POINTS:
        return [int(round(v)) for v in _naive_forecast(series, steps)]

    fit = _fit_best_arima(series)
    if fit is None:
        return [int(round(v)) for v in _naive_forecast(series, steps)]

    try:
        forecast = np.asarray(fit.forecast(steps=steps), dtype=float)
        forecast = np.clip(forecast, 0, None)
        return [int(round(v)) for v in forecast]
    except Exception:
        return [int(round(v)) for v in _naive_forecast(series, steps)]


def predict_next_hour(values):
    """One-step-ahead forecast; returns None when there is no data at all."""
    series = _clean(values)
    if len(series) == 0:
        return None
    return predict_full_day(series, steps=1)[0]
