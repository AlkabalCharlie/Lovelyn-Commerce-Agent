"""Final demonstration: TWO product-specific review videos, NOT uploaded.
1. Be Free from Debt (digital)   -> verify-product-debt.mp4
2. TradingView (software)        -> verify-product-tradingview.mp4
"""
from dotenv import load_dotenv
load_dotenv()

from services.product_video import build_brief, build_script
from services.product_video_render import render_product_short

# --- Video 1: Be Free from Debt (digital, owned) ---
debt = build_brief(
    campaign_id="66d125ce-0523-492b-9679-3bd06d75e1be",
    product_name="Be Free from Debt",
    merchant="Payhip",
    product_url="https://payhip.com/b/debt-guide",
    affiliate_url=None,
    description="50+ page debt payoff workbook: zero-based budgeting, 50/30/20, envelope system.",
    price="$7.00",
)
debt_script = build_script(debt)
print("DEBT script beats:", [s["beat"] for s in debt_script["scenes"]])
out1 = render_product_short(debt, debt_script,
                            "media/shorts/verify-product-debt.mp4")
print("DEBT RESULT:", out1)

# --- Video 2: TradingView (software, affiliate) ---
tv = build_brief(
    campaign_id="b8d56c20-c801-4c97-ac8f-936bb5c36cba",
    product_name="TradingView",
    merchant="TradingView",
    product_url="https://tradingview.com",
    affiliate_url="https://tradingview.com/?aff=lovelyn",
    description="Charting platform with indicators, alerts and community scripts.",
    price=None,
)
tv_script = build_script(tv)
print("TV script beats:", [s["beat"] for s in tv_script["scenes"]])
out2 = render_product_short(tv, tv_script,
                            "media/shorts/verify-product-tradingview.mp4")
print("TV RESULT:", out2)
