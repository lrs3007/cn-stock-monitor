"""Small ctypes binding to the same TA-Lib C library on desktop and Android.

Only the binding changes: formulas, defaults, output ordering and lookback are
provided by TA-Lib. No approximate Python replacement indicators are used.
"""
import ctypes as ct
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

_metadata = json.loads(Path(__file__).with_name('talib_metadata.json').read_text())
_functions = _metadata['functions']
_lib = ct.CDLL(os.environ['MONITOR_TALIB_LIBRARY'])
_lib.TA_GetVersionString.restype = ct.c_char_p
__ta_version__ = _lib.TA_GetVersionString()
if __ta_version__.decode().split()[0] != _metadata['version']:
    raise RuntimeError('TA-Lib library and indicator metadata versions differ')
if _lib.TA_Initialize() != 0:
    raise RuntimeError('TA-Lib initialization failed')


def get_function_groups():
    result = {}
    for name, item in _functions.items():
        result.setdefault(item['info']['group'], []).append(name)
    return result


class Function:
    def __init__(self, name):
        self.name = name.upper()
        item = _functions[self.name]
        self.info = item['info']
        self.parameters = self.info['parameters'].copy()
        self.output_names = list(self.info['output_names'])
        self.inputs = [field for entry in self.info['input_names'].values()
                       for field in (entry if isinstance(entry, list) else [entry])]
        self.integers = item['integer_outputs']
        self.option_types = [ct.c_int if isinstance(v, int) else ct.c_double for v in self.parameters.values()]
        self.call = getattr(_lib, 'TA_' + self.name)
        self.call.restype = ct.c_int
        self.call.argtypes = ([ct.c_int, ct.c_int] + [ct.c_void_p] * len(self.inputs) + self.option_types
                             + [ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)] + [ct.c_void_p] * len(self.output_names))
        self.lookback = getattr(_lib, 'TA_' + self.name + '_Lookback')
        self.lookback.argtypes = self.option_types
        self.lookback.restype = ct.c_int

    def __call__(self, arrays, **kwargs):
        if any(k not in self.parameters for k in kwargs):
            raise ValueError('Unknown indicator parameter')
        params = {**self.parameters, **kwargs}
        options = list(params.values())
        if self.lookback(*options) < 0:
            raise ValueError('Invalid TA-Lib parameters')
        inputs = [np.ascontiguousarray(arrays[field], dtype=np.float64) for field in self.inputs]
        size = len(inputs[0])
        if any(len(v) != size for v in inputs):
            raise ValueError('Input array lengths differ')
        result = [np.zeros(size, dtype=np.int32) if integer else np.full(size, np.nan)
                  for integer in self.integers]
        if size:
            # Match the Python binding's handling of leading missing inputs.
            valid = np.logical_and.reduce([~np.isnan(value) for value in inputs])
            start = int(np.argmax(valid)) if valid.any() else size
            if start < size:
                buffers = [np.empty(size, dtype=value.dtype) for value in result]
                begin, count = ct.c_int(), ct.c_int()
                sliced = [value[start:] for value in inputs]
                code = self.call(0, size - start - 1, *[v.ctypes.data for v in sliced], *options,
                                 ct.byref(begin), ct.byref(count), *[v.ctypes.data for v in buffers])
                if code:
                    raise ValueError(f'TA-Lib {self.name} failed: {code}')
                for output, buffer in zip(result, buffers):
                    output[start + begin.value:start + begin.value + count.value] = buffer[:count.value]
        return result[0] if len(result) == 1 else result


abstract = SimpleNamespace(Function=Function)


def __getattr__(name):
    if name not in _functions:
        raise AttributeError(name)
    def calculate(*args, **kwargs):
        fn = Function(name)
        if len(args) < len(fn.inputs):
            raise ValueError('Missing price input')
        arrays = dict(zip(fn.inputs, args[:len(fn.inputs)]))
        options = dict(zip(fn.parameters, args[len(fn.inputs):]))
        return fn(arrays, **{**options, **kwargs})
    return calculate
