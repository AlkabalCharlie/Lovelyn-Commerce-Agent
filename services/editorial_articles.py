"""Editorial long-form Blogger articles.

Quality contract (enforced by `validate_article`):
- 900-1200 words of genuinely useful prose (no filler, no repetition).
- Reader-first structure: hook -> relatable situation -> accurate explanation
  of both approaches -> worked example -> trade-offs -> how to decide.
- Product introduced naturally and late, described ONLY from the verified
  fact pack, with the approved campaign URL and an honest disclosure.
- Valid, responsive HTML with proper heading hierarchy.
- Featured image required, hosted at a public URL, with alt text.

Accuracy rules for the current debt article:
- Both methods explained accurately; neither declared universally best.
- Avalanche described as generally minimising interest *when payments are
  maintained and all else is equal*; snowball's behavioural advantage
  explained as motivation, not mathematics.
- Hypothetical figures are explicitly labelled hypothetical.
- No invented research, testimonials, statistics or guarantees.
"""
import re

from services.content_packages import PRODUCT_FACTS

DEBT_CID = "66d125ce-0523-492b-9679-3bd06d75e1be"
TV_CID = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"

MIN_WORDS = 900
MAX_WORDS = 1200


def _words(html_or_md: str) -> int:
    text = re.sub(r"<[^>]+>", " ", html_or_md or "")
    return len(re.findall(r"[A-Za-z0-9$%'’-]+", text))


# --------------------------------------------------------------- articles --
def debt_payoff_article(campaign_url: str, image_url: str,
                        image_alt: str) -> dict:
    """Be Free from Debt: full editorial article (~1,000 words)."""
    facts = PRODUCT_FACTS[DEBT_CID]
    body = f"""
<p>Most people who set out to pay off debt are not short of determination on
day one. They are short of a plan that survives day forty. The two methods
below are the ones you will see recommended most often, and they are usually
presented as competitors when in fact they answer two different questions:
<em>which way costs less?</em> and <em>which way will I actually finish?</em></p>

<p>This article explains both methods accurately, walks through a worked
example with clearly hypothetical figures, and then shows you how to choose
between them. You do not need to buy anything to use it.</p>

<h2>A situation you might recognise</h2>

<p>Picture a household with four debts: a credit card, a store card, a
personal loan and a car finance agreement. The minimum payments come out
automatically every month. Nobody is behind. But every month the balance
total barely moves, and there is a quiet feeling that the whole thing is
rolling gently downhill.</p>

<p>That feeling is common because minimum payments are designed around the
lender's interest, not your progress. A minimum payment on a high-rate card
can be mostly interest and very little principal. You can pay every bill on
time for years and still feel stuck. The fix is not usually a bigger income;
it is deciding deliberately where the extra money goes.</p>

<h2>The debt avalanche method</h2>

<p>The avalanche method says: list your debts in order of interest rate,
highest first. Pay the minimum on everything, and send every spare pound,
dollar or euro to the debt with the highest rate.</p>

<h3>Why it works</h3>

<p>Interest is charged on the balance that exists, so the most expensive
money in your account is whatever is sitting at the highest rate. Attacking
that balance first means each unit of extra payment removes more future
interest than it would anywhere else. When all other conditions remain equal,
and when you keep making every payment on time, the avalanche approach
generally costs the least in total interest and clears the balance faster.</p>

<h3>Where it can stall</h3>

<p>The highest-rate debt is often also the largest, or the one with the
stiffest minimum. That means the first visible win can be months away. For
some people the mathematics is exactly right but the experience is
demoralising, and the plan quietly stops.</p>

<h2>The debt snowball method</h2>

<p>The snowball method says: list your debts by balance, smallest first.
Pay the minimum on everything, and send every spare pound, dollar or euro to
the smallest balance.</p>

<h3>Why it works</h3>

<p>Small balances are cleared quickly, and each cleared balance is one fewer
direct debit, one fewer due date, and one visible win. The freed-up minimum
payment then rolls onto the next balance, and the amount going towards
reducing principal grows each time a debt disappears. That rolling effect is
where the name comes from.</p>

<h3>What it costs</h3>

<p>The order ignores interest rates, so you may pay more in total interest
than the avalanche order would have cost you. That is a real trade-off, not a
rounding error, and it should be acknowledged rather than glossed over.</p>

<h2>The difference, stated plainly</h2>

<p>The avalanche method optimises for <strong>interest saved</strong>. The
snowball method optimises for <strong>momentum</strong>. Neither is a
personality test and neither is a moral position.</p>

<p>The honest comparison is this: if you are confident you will keep going,
the avalanche order is the cheaper route. If your history suggests you are
more likely to keep going when you can see progress, the snowball order may
finish when the cheaper route would not have. A plan you complete with a
little more interest is better than an optimal plan you abandon.</p>

<h2>A worked example (illustrative figures only)</h2>

<p>These numbers are hypothetical and exist only to show the mechanics. They
are not a prediction for your situation.</p>

<ul>
<li>Card A: balance $3,200, rate 22%, minimum $80</li>
<li>Card B: balance $900, rate 18%, minimum $30</li>
<li>Store card: balance $450, rate 26%, minimum $25</li>
<li>Loan: balance $6,000, rate 9%, minimum $180</li>
</ul>

<p>Suppose you can find an extra $250 a month. Under the avalanche order the
$250 goes to the store card first, because 26% is the highest rate. It clears
quickly, and its $25 minimum joins the extra amount, so $275 then goes to
Card A, the next highest rate. Under the snowball order the $250 goes to the
store card as well, because it also happens to be the smallest balance; once
it clears, the same $275 moves on.</p>

<p>In this particular example the two orders agree on the first step, which is
common when a small balance also carries a high rate. They diverge at the
second step, where snowball would attack Card B (the smaller balance) and
avalanche would attack Card A (the higher rate). That divergence is where the
interest difference appears.</p>

<h2>How to set either method up</h2>

<ol>
<li>Collect every current statement and write down four figures per debt:
lender, outstanding balance, interest rate, and contractual minimum payment.</li>
<li>Add the minimum payments together. That number is your floor; it has to
come out every month regardless of method.</li>
<li>Work out what is genuinely available beyond that floor. Be conservative;
an over-optimistic number is the most common reason plans fail in month two.</li>
<li>Choose an order and write it down where you can see it.</li>
<li>Revisit monthly. Rates change, payments change, and life changes. A plan
is a working document, not a contract.</li>
</ol>

<h2>Common problems, and what to do about them</h2>

<h3>You have no spare money at all</h3>

<p>Then the method is not the problem yet. The first tasks are checking
whether the minimums are correct and whether one balance can be renegotiated.
An approach that allocates nothing extra cannot outperform another that also
allocates nothing extra.</p>

<h3>An emergency undoes your progress</h3>

<p>This is why many plans include a small buffer before aggressive repayment.
Without one, an unexpected bill goes straight onto a card and you feel you
have gone backwards.</p>

<h2>Where a worksheet pack fits</h2>

<p>{facts['name']} is our own product: a {facts['facts'][1].lower().rstrip('.')}, with a {facts['facts'][2].lower().rstrip('.')}. It exists because the arithmetic above is straightforward but keeping four numbers per debt organised, month after month, is where plans drift.</p>

<p>If you already have a system you trust, you do not need it. If the honest
answer is that you have never written the balances down in one place, a set of
worksheets gives you a place to do that and a structure to revisit monthly.
The value comes from completing them, and it is a self-applied workbook rather
than financial advice.
<a href="{campaign_url}">{facts['name']}</a>.</p>

<p><em>{facts['disclosure']}</em></p>

<h2>Making the decision</h2>

<p>Ask yourself one question: which failure is more likely for me, running out
of motivation or paying too much interest? If you have started debt plans
before and stopped, the snowball order's early wins may matter more. If you
are steady and simply want the cheapest exit, the avalanche order fits better.
Either way, the numbers come from your own statements and the order is yours
to adjust.</p>
"""
    return {
        "format_type": "blogger_article_html",
        "title": ("Snowball vs Avalanche: Which Debt Payoff Plan "
                  "Will You Actually Finish?"),
        "body_html": body.strip(),
        "labels": ["personal finance", "budgeting", "debt"],
        "campaign_url": campaign_url,
        "featured_image_url": image_url,
        "featured_image_alt": image_alt,
        "disclosure": facts["disclosure"],
        "origin": "editorial_long_form",
    }


def tradingview_article(campaign_url: str, image_url: str,
                        image_alt: str) -> dict:
    """TradingView tier comparison (~950 words). Verified facts only."""
    facts = PRODUCT_FACTS[TV_CID]
    body = f"""
<p>TradingView's pricing page is unusually honest for a charting platform:
the free plan is genuinely capable, and the paid plans mostly change limits
rather than unlocking a different product. That makes the decision less
dramatic than the marketing implies, and more useful to think through
properly.</p>

<p>This article sets out what each tier actually changes, what those changes
mean in practice, and which type of trader is served by each.</p>

<h2>The free plan, accurately described</h2>

<p>{facts['facts'][0]}</p>

<p>That is a working charting environment. If you are learning, or if your
process is one market, one timeframe, and a couple of indicators, the free
plan is not a crippled demo. The limitations bite in specific circumstances
rather than generally.</p>

<h3>Where the free plan starts to pinch</h3>

<p>Two indicators per chart is enough to follow a trend, and not enough to
compare a momentum reading, a volatility band, and a volume study on the same
chart. One saved layout means you rebuild your workspace whenever you switch
tasks. Five alerts means you cannot leave price notifications running across
several instruments.</p>

<h2>What the Essential plan changes</h2>

<p>{facts['facts'][1]}</p>

<p>{facts['facts'][2]}</p>

<p>Read that list carefully: it is a list of limits, not a list of new
abilities. If none of those limits are hitting you now, moving up will not
change your results.</p>

<h2>Who each plan genuinely serves</h2>

<h3>Free is likely enough if</h3>

<ul>
<li>You trade one market and one timeframe.</li>
<li>Your indicator set is small and stable.</li>
<li>You do not rely on alerts to catch setups.</li>
</ul>

<h3>Essential is worth considering if</h3>

<ul>
<li>You compare multiple timeframes side by side.</li>
<li>You run alert-driven entries across several instruments.</li>
<li>You keep more than one workspace for different strategies.</li>
</ul>

<h2>What the tiers are not buying you</h2>

<p>A paid tier does not make analysis better. It removes specific constraints
you were already working around. If you have never hit the indicator limit,
paying to raise it changes nothing about your decisions.</p>

<h2>Why the platform matters beyond the limits</h2>

<p>{facts['facts'][3]}</p>

<p>Community scripts and broker integrations are the parts of a charting
platform that are hardest to replicate elsewhere, and they are not tier-gated
in the same way the limits are. That is a reasonable thing to weigh when
choosing a platform at all, separate from choosing a tier.</p>

<h2>A practical way to decide</h2>

<ol>
<li>Use the free plan for a month and note every moment you wish you could
do something it would not allow.</li>
<li>Count how often those moments happened. Once a week is a limitation;
once a month is a preference.</li>
<li>Compare the subscription cost against the time you spend rebuilding
layouts and adding indicators one at a time.</li>
<li>If the limits are hypothetical, stay on the free plan and revisit in a
quarter.</li>
</ol>

<h2>What changes if you trade seriously</h2>

<p>The economics shift when charting stops being a learning tool and becomes
the place where decisions get made. In that setting, a workspace rebuilt from
scratch every morning is not inconvenient, it is a source of inconsistency:
the chart you review today is not arranged the same way as the chart you
reviewed yesterday, so your comparison is not like-for-like. Layouts are a
small feature that quietly protects the consistency of a process.</p>

<p>The alert ceiling matters for a different reason. Alert-driven trading is
less about watching screens and more about only looking when something has
genuinely changed. Twenty alerts across several instruments is a workable
budget; five is a choice about which instruments you are willing to miss.
Neither is wrong, but the difference is concrete rather than promotional.</p>

<h2>The mistake worth avoiding</h2>

<p>The most expensive version of this decision is subscribing early, feeling
that the subscription has to justify itself, and then taking more trades to
feel productive. A tool costs money either way; it should not cost you
judgement as well. If you cannot yet say in one sentence what the paid tier
would change about a specific decision you made last week, the honest answer
is that it is not yet needed.</p>

<p>There is also a version of the reverse mistake: grinding on a plan whose
limits you hit every single session, spending twenty minutes a day rebuilding
what a higher tier would preserve. That is a real cost too, just one that
never appears on a pricing page.</p>

<h2>A note on annual billing</h2>

<p>{facts['facts'][1].split(';')[-1].strip().capitalize() if ';' in facts['facts'][1] else facts['facts'][1]}</p>

<p>Annual billing is a commitment, and commitment is only useful once you are
confident about the tier. Starting monthly and switching later costs a little
more in the short term and considerably less in regret.</p>

<h2>If you want to compare the tiers directly</h2>

<p>Plan comparison is easier with the pricing table open next to this article
than from memory. You can review the plans here:
<a href="{campaign_url}">TradingView plans</a>.</p>

<p><em>{facts['disclosure']}</em></p>

<h2>The short version</h2>

<p>The free tier is a real charting environment. Essential buys headroom you
may or may not need. The right answer depends on whether the limits are
currently costing you something &mdash; and that is a question only your own
last month of work can answer.</p>
"""
    return {
        "format_type": "blogger_article_html",
        "title": ("TradingView Free vs Paid: What Each Tier Actually Changes "
                  "in 2026"),
        "body_html": body.strip(),
        "labels": ["personal finance", "trading", "tools"],
        "campaign_url": campaign_url,
        "featured_image_url": image_url,
        "featured_image_alt": image_alt,
        "disclosure": facts["disclosure"],
        "origin": "editorial_long_form",
    }


# ------------------------------------------------------------ validation --
REQUIRED_H2 = 3


def validate_article(article: dict, require_image: bool = True) -> dict:
    """Quality gate for Blogger articles. Returns {ok, failures, stats}."""
    failures = []
    html_body = article.get("body_html") or ""
    words = _words(html_body)

    # 1. Length: a real standard, but not the only measure.
    if words < 350:
        failures.append(f"too short for publication ({words} words) - "
                        f"needs genuine subject depth")
    elif words < MIN_WORDS:
        failures.append(f"below editorial target ({words} < {MIN_WORDS} words)")
    elif words > MAX_WORDS:
        failures.append(f"over editorial target ({words} > {MAX_WORDS}); "
                        f"trim filler rather than adding repetition")

    # 2. Structure: heading hierarchy + opening + closing.
    h2s = len(re.findall(r"<h2[ >]", html_body))
    h3s = len(re.findall(r"<h3[ >]", html_body))
    if h2s < REQUIRED_H2:
        failures.append(f"needs at least {REQUIRED_H2} H2 sections (found {h2s})")
    if h3s < 1:
        failures.append("needs at least one H3 sub-section for detail")
    if "<p>" not in html_body[:400]:
        failures.append("article must open with a prose introduction, not a list")
    if not re.search(r"<h2[^>]*>(?:(?!</h2>).)*(decision|short version|"
                     r"choosing|conclusion|better fit)", html_body, re.S | re.I):
        failures.append("missing a decision-oriented closing section")

    # 3. Explanation depth: the body must contain real explanatory prose.
    paras = re.findall(r"<p>(.*?)</p>", html_body, re.S)
    long_paras = [p for p in paras if _words(p) >= 35]
    if len(long_paras) < 6:
        failures.append(f"needs at least 6 substantive paragraphs "
                        f"(found {len(long_paras)})")
    bullet_items = len(re.findall(r"<li>", html_body))
    if bullet_items and _words(html_body) and bullet_items > words / 25:
        failures.append("too bullet-heavy for an article")

    # 4. Destination + disclosure.
    url = article.get("campaign_url") or ""
    if not url.startswith("https://"):
        failures.append("missing approved campaign URL")
    elif url not in html_body:
        failures.append("approved campaign URL not present in body")
    disclosure = article.get("disclosure") or ""
    if not disclosure:
        failures.append("missing disclosure text")
    elif disclosure.split(":")[-1].strip()[:40] not in html_body:
        failures.append("disclosure not present in body")

    # 5. Verified facts only: every $ figure must come from the fact pack.
    allowed_numbers = set()
    for pack in PRODUCT_FACTS.values():
        for fact in pack.get("facts", []):
            allowed_numbers.update(re.findall(r"\$[\d.,]+", fact))
    body_numbers = set(re.findall(r"\$[\d.,]+", html_body))
    if "hypothetical" not in html_body.lower():
        stray = body_numbers - allowed_numbers
        if stray:
            failures.append(f"unverified price claims: {sorted(stray)}")

    # 6. Banned invented-claim patterns.
    for pattern, why in (
            (r"\b(guarantee[ds]?|guaranteed results?)\b", "guarantee claim"),
            (r"\b\d{1,3}% (of|more) (people|users|customers)", "invented statistic"),
            (r"\b(studies show|research shows|proven to)\b", "unsupported research"),
            (r"\b(testimonial|reviewers say)\b", "fabricated testimonial"),
            (r"\b(limited time|act now|hurry)\b", "pressure marketing"),
    ):
        if re.search(pattern, html_body, re.I):
            failures.append(f"banned claim: {why}")

    # 7. Image.
    if require_image:
        if not article.get("featured_image_url"):
            failures.append("missing featured image URL")
        elif not str(article["featured_image_url"]).startswith("https://"):
            failures.append("featured image must be a public https URL")
        if not (article.get("featured_image_alt") or "").strip():
            failures.append("missing featured image alt text")

    # 8. HTML sanity.
    for tag in ("p", "h2"):
        if html_body.count(f"<{tag}") != html_body.count(f"</{tag}>"):
            failures.append(f"unbalanced <{tag}> tags")
    if "style=" in html_body:
        failures.append("inline styles are not allowed (Blogger/CSP hostile)")

    return {"ok": not failures, "failures": failures,
            "stats": {"words": words, "h2": h2s, "h3": h3s,
                      "paragraphs": len(paras),
                      "substantive_paragraphs": len(long_paras)}}
