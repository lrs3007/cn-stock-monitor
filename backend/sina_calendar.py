"""Strict Python port of the calendar-only branch of AKShare's Sina decoder.

Derived from hk_js_decode (AKShare, MIT; license in vendor/AKShare-LICENSE).
Unlike the original multi-format decoder this accepts only calendar format 139.
No JavaScript or network-supplied code is executed.
"""
from datetime import date, timedelta

ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


def decode_calendar(encoded):
    if not isinstance(encoded, str) or not encoded or len(encoded) > 100000:
        raise ValueError('交易日历编码无效')
    try:
        values = [ALPHABET.index(char) for char in encoded]
    except ValueError:
        raise ValueError('交易日历包含未知编码') from None
    position = 0

    def bits(length):
        nonlocal position
        if length < 0 or length > 30 or position + length > len(values) * 6:
            raise ValueError('交易日历编码被截断')
        result = 0
        for shift in range(length):
            result |= ((values[position // 6] >> (position % 6)) & 1) << shift
            position += 1
        return result

    if bits(12) != 139 or (63 ^ bits(6)) > 1:
        raise ValueError('交易日历编码版本不支持')
    day, end = bits(18) - 1, bits(18)
    if not 0 <= end - day <= 100000:
        raise ValueError('交易日历范围无效')
    width, remaining, result = 0, -1, []
    epoch = date(1970, 1, 1) + timedelta(days=7657)
    while day < end:
        day += 1
        weekday = day % 7
        if weekday in (3, 4):
            day += 5 - weekday
        stamp = epoch + timedelta(days=day)
        if remaining <= 0:
            if bits(1):
                sign = 2 * bits(1) - 1
                length = 1
                while bits(1):
                    length += 1
                width += length * sign
            remaining = bits(3 * width) + 1
            if not result:
                result.append(stamp)
                remaining -= 1
        else:
            result.append(stamp)
        remaining -= 1
    if not result:
        raise ValueError('交易日历为空')
    return result
