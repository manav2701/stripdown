# What is actually reachable for demand research

Checked before this command was designed, so it is not designed around a
source that turns out to be closed.

## Usable

| Source | Status |
|---|---|
| **Your git history and codebase** | local, free, complete. The scope diff and timeline come from here, and they are the only *measured* output of this command |
| **Competitor pricing and docs pages** | public, fetchable, citable. The backbone of the competitor matrix. Grade B |
| **Hacker News (Algolia)** | `https://hn.algolia.com/api/v1/`, free, no auth, roughly 10k requests/hour per IP by third-party reports. An undocumented result-count cap exists. Grade C |
| **GitHub issue and PR search** | available in-session. Best source of *workaround evidence* — users describing how they route around a feature, which is a documented removal signal. Grade C |
| **App Store / Play review feeds** | public RSS/JSON, where the product is a mobile app. Grade C |
| **Public changelogs** | fetchable and dated, which makes them unusually good evidence. Grade B |

## Not usable, and why

**Google Trends.** The official API has been an application-only alpha since
July 2025 with no production guarantees, and `pytrends` is archived and returns
HTTP 429. Do not build a claim on it. Also note it returns *relative* search
interest, not query counts, so even working access would not support the claims
people make from it.

**Reddit.** Free only for non-commercial use at roughly 100 queries/minute,
with pre-approval tightening under the November 2025 Responsible Builder
Policy; commercial access is a negotiated contract with no public rate card.
Sources disagree on whether the public API closes in late 2026 or 2027. Not
usable for a tool other people run commercially. If a user brings a specific
thread they opened themselves, cite that as grade C.

**G2, Capterra, TrustRadius.** The richest "I wish it did X" corpus anywhere,
and all three prohibit scraping. They are also biased: vendors solicit reviews,
sometimes with incentives tied to minimum word counts, which skews which
products accumulate them, and G2's own guidelines describe reviews as
subjective and incomplete rather than expert assessment. If a user pastes or
exports reviews themselves, that is grade C *with the bias stated in the same
sentence*.

## The part no source fixes

None of this tells you what the market wants. It tells you what competitors
shipped and what some people said in public. The widely cited statistic that
most features go unused is vendor research on customer-defined feature tags,
measured by daily volume, which structurally penalises features that are
occasional but important — so it is directional at best and not a law.

Demand is established by talking to people who would pay. A scope diff narrows
*what to ask about*. It does not answer the question, and this command should
say so every time it runs.
