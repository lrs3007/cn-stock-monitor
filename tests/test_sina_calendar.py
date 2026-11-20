import hashlib
import re
from pathlib import Path
import pytest
from backend.sina_calendar import decode_calendar


def test_full_calendar_matches_original_javascript_decoder():
    # Independently compared all 8796 dates with AKShare's original MiniRacer decoder.
    encoded = re.search(r'"(.*?)"', (Path(__file__).parent/'fixtures/sina_calendar.txt').read_text()).group(1)
    dates = decode_calendar(encoded)
    assert len(dates) == 8796
    assert str(dates[0]) == '1990-12-19'
    assert str(dates[-1]) == '2026-12-31'
    assert len(set(dates)) == len(dates)
    assert all(date.weekday() < 5 for date in dates)
    assert hashlib.sha256('\n'.join(map(str, dates)).encode()).hexdigest() == 'd9acb615f0c7e4ccc72ea4bffb5f014a8d9416c9a1fcf20c9740507583d26160'


@pytest.mark.parametrize('encoded', ['', None, '!', 'LC/', 'AAAA', 'A'*100001])
def test_calendar_rejects_bad_input(encoded):
    with pytest.raises(ValueError): decode_calendar(encoded)
