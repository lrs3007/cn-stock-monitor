import os
import pytest
import pandas as pd

os.environ['MONITOR_TEST']='1'


@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setenv('MONITOR_DB',str(tmp_path/'test.sqlite3'))
    from backend import storage
    storage.initialize()
    return storage


@pytest.fixture(scope='session')
def market():
    from backend.market import DemoProvider
    return DemoProvider().fetch('510300.SH',pd.Timestamp('2026-11-06 14:37'))
