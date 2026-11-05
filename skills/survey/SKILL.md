---
description: Generate an awareness and perceived-value survey for a specific feature, to tell a discovery problem apart from a value problem. Use when a feature has low adoption and the user needs to know whether people cannot find it or do not want it.
when_to_use: A feature came back as reposition or discoverability-suspect, or the user asks whether low adoption is because users do not know about a feature or because they do not value it.
argument-hint: "<feature-id>"
allowed-tools:
  - Bash(python3 *)
  - Read
  - Write
---

# strip-down: survey

Generate the instrument that event data cannot replace.

## Why this exists

A quiet feature is either a **discoverability failure** (users would value it
but don't know it exists or can't find it) or a **value failure** (they know
and don't want it). These have opposite fixes: one is a placement problem, the
other is a removal candidate.

Breadth and depth give you the behavioural *signature*. They cannot give you
awareness, because awareness is not a behaviour — nobody emits an event for
"did not know this existed". So this is the one question in strip-down that
requires asking humans, and the plugin generates the instrument rather than
pretending to answer it.

There is a heuristic in circulation that under 40% awareness means a discovery
problem and over 70% means a value problem. It is one blog's own cutoff with no
validation behind it. Offer it as a rough frame if the user wants a number, and
label it as unvalidated. Do not present it as a standard.

## 1. Gather what is known

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verdict_report.py" --aggregate usage.csv --window-days 400
```

Pull the row for the feature: breadth, depth, bucket, and the behavioural
hypothesis. The survey is designed to *test* that hypothesis, not to restate it.

## 2. Write the survey

Write it to `.stripdown/surveys/<feature-id>.md`. Four sections, in this order,
because the order matters:

**A. Unprompted awareness — ask this first and do not reveal the feature.**
> "When you need to <the job the feature does>, how do you currently do it?"

An open question, before the feature is named. If people describe a workaround,
that is the single most useful answer you can get: users routinely working
around a feature is a documented removal signal, and it also tells you the
feature is not findable.

**B. Prompted awareness.**
> "Before today, did you know <product> could <do the thing>?"
> Yes, and I've used it / Yes, but I've never used it / No / Not sure

The split between the first two options separates discovery from adoption.

**C. Perceived value — ask only those who said no or never used it.**
> "Now that you know it exists, how useful would it be to you?"
> Not at all / Slightly / Moderately / Very / Essential

High awareness plus low perceived value is a value failure. Low awareness plus
high perceived value is a discovery failure. That 2x2 is the whole point of the
exercise.

**D. One open question.**
> "If it disappeared tomorrow, what would you do instead?"

This surfaces the dependency nobody logged, and it is the question whose answers
most often change a removal decision.

## 3. Say how to run it, and the sampling trap

State these plainly, because a survey run badly is worse than no survey — it
produces a number people will quote.

- **Ask non-adopters, not everyone.** The question is about people who did not
  use the feature. Surveying adopters tells you nothing about awareness.
- **In-product beats email** for awareness questions: email respondents are
  your most engaged users and will over-report awareness.
- **Churned users are the people you most need and cannot reach.** Say so. A
  feature whose absence drove someone away leaves no trace in your analytics
  *and* no trace in a survey of current users.
- **Target a usable sample.** Under ~100 responses the awareness percentage
  carries an interval wide enough to span both hypotheses, which means it
  cannot distinguish them. Say what the interval would be rather than letting
  someone act on 12 responses.
- **Do not lead.** "Did you know about our powerful export feature?" measures
  nothing.

## 4. After it runs

Offer to record the result in the feature's `notes` in the inventory, and — if
the answer is that awareness was high and value was low — to re-run
`/strip-down:verdict`, where it becomes evidence rather than a hypothesis.

Do not interpret survey results you have not been given. If the user has not run
it yet, say what the two outcomes would mean and stop.
