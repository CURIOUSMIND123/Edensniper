"""Round-trip charges for buying and selling an index option (Groww, NSE/BSE).

Rates as published for 2025-26. Check Groww's charges page before relying on them.
"""

BROKERAGE_PER_ORDER = 20.0      # Groww F&O: flat Rs 20 per executed order
STT_SELL = 0.001                # 0.1% of premium, on the sell side
TXN = {"NSE": 0.0003503, "BSE": 0.000325}  # exchange transaction charge on premium turnover
SEBI = 10 / 1e7                 # Rs 10 per crore
STAMP_BUY = 0.00003             # 0.003% on the buy side
GST = 0.18                      # on brokerage + exchange + SEBI charges


def round_trip(buy_value: float, sell_value: float, exchange: str = "NSE", orders: int = 2) -> float:
    """Total charges in rupees for one buy and one sell. Values are premium x quantity."""
    brokerage = orders * BROKERAGE_PER_ORDER
    turnover = buy_value + sell_value
    txn = TXN.get(exchange, TXN["NSE"]) * turnover
    sebi = SEBI * turnover
    stt = STT_SELL * sell_value
    stamp = STAMP_BUY * buy_value
    gst = GST * (brokerage + txn + sebi)
    return round(brokerage + txn + sebi + stt + stamp + gst, 2)
