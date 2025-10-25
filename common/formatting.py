from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Union

getcontext().prec = 40  # plenty of headroom

def to_decimal_str(x: Union[float, str, Decimal], places: int) -> str:
    """
    Return a non-scientific, trimmed decimal string with exactly `places` decimals.
    No trailing zeros beyond `places`. Use ROUND_DOWN for safety.
    """
    d = Decimal(str(x))
    q = Decimal(10) ** -places
    d = d.quantize(q, rounding=ROUND_DOWN)  # enforce lot/tick
    s = format(d, f"f")                     # force non-scientific
    # Trim trailing zeros *only if* you prefer minimal form; but keep exactly `places` is also OK.
    # If you want minimal (docs recommend removing trailing zeros), do:
    if '.' in s:
        s = s.rstrip('0').rstrip('.') or "0"
    return s
