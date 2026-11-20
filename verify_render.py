"""Milestone C verification: render one REAL MP4 from a queued package."""
from dotenv import load_dotenv
load_dotenv()

from services.shorts_renderer import render_short

pkg = {
    "title": "Snowball vs Avalanche: pick your debt payoff plan",
    "hook": "Your debt payoff fails at the plan, not the motivation.",
    "scenes": [
        {"scene": 1, "on_screen": "Snowball or Avalanche?",
         "narration": "Your debt payoff fails at the plan, not the motivation. Here is the one page fix."},
        {"scene": 2, "on_screen": "Snowball: smallest balance first. Quick wins, strong momentum.",
         "narration": "Snowball pays the smallest balance first, for quick wins and momentum."},
        {"scene": 3, "on_screen": "Avalanche: highest interest rate first. Saves the most money.",
         "narration": "Avalanche pays the highest interest rate first, and saves the most money."},
        {"scene": 4, "on_screen": "Pick the one you will actually finish.",
         "narration": "The method you abandon is the one that costs you. Pick the one you will finish."},
        {"scene": 5, "on_screen": "Get the worksheet pack. Link below.",
         "narration": "Get the debt worksheet pack at the link below. Disclosure: this is our own product."},
    ],
    "description": "Snowball vs avalanche debt payoff explained. Disclosure: our own product.",
    "tags": ["debt payoff", "budgeting"],
}
out = render_short(pkg, "media/shorts/verify-debt-short.mp4")
print("RESULT:", out)
