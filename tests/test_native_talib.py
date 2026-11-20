"""Compare the Android binding with the desktop binding, across all indicators."""
import os
import importlib
import numpy as np
import pandas as pd
import pytest
import talib
from talib import abstract


@pytest.fixture(scope='module')
def native():
    old = os.environ.get('MONITOR_TALIB_LIBRARY')
    os.environ['MONITOR_TALIB_LIBRARY'] = talib._ta_lib.__file__
    result = importlib.import_module('backend.native_talib')
    if old is None: os.environ.pop('MONITOR_TALIB_LIBRARY')
    else: os.environ['MONITOR_TALIB_LIBRARY'] = old
    return result


@pytest.mark.parametrize('name', [n for n in talib.get_functions() if n != 'MAVP'])
def test_android_binding_matches_desktop(native, market, name):
    arrays = {key: market.minute[key].to_numpy(dtype=float) for key in ('open', 'high', 'low', 'close', 'volume')}
    expected = abstract.Function(name)(arrays)
    actual = native.Function(name)(arrays)
    for left, right in zip(expected if isinstance(expected, list) else [expected], actual if isinstance(actual, list) else [actual]):
        np.testing.assert_allclose(right, left, rtol=1e-12, atol=1e-12, equal_nan=True)


def test_custom_indicators_use_native_binding(native, market, monkeypatch):
    from backend import indicators
    expected = {name: indicators.calculate(market.minute, name) for name in indicators.CUSTOM}
    monkeypatch.setattr(indicators, 'talib', native)
    monkeypatch.setattr(indicators, 'abstract', native.abstract)
    for name, frame in expected.items():
        pd.testing.assert_frame_equal(indicators.calculate(market.minute, name), frame, rtol=1e-12, atol=1e-12)


def test_custom_parameters(native, market):
    arrays = {key: market.minute[key].to_numpy(dtype=float) for key in ('open', 'high', 'low', 'close', 'volume')}
    for name, params in [('RSI', {'timeperiod': 6}), ('MACD', {'fastperiod': 8, 'slowperiod': 21}), ('BBANDS', {'timeperiod': 26, 'nbdevup': 2.5})]:
        left, right = abstract.Function(name)(arrays, **params), native.Function(name)(arrays, **params)
        np.testing.assert_allclose(right, left, rtol=1e-12, atol=1e-12, equal_nan=True)
    with pytest.raises(ValueError): native.Function('RSI')(arrays, timeperiod=-1)
