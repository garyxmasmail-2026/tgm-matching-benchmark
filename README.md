# A benchmark for multi-hop matching in mutual-credit networks

Mutual-credit and time-banking networks have run for forty years, and almost all of them clear bilaterally: one person's need meets one person's offer. The economically interesting exchanges are the ones nobody is positioned to see — a chain of three or four parties where the first never meets the last, a set of offers that are individually insufficient and jointly adequate, a resource idle in one country that answers a need in another.

Those are computationally discoverable. In the field, they are almost never discovered.

The obstacle to improving on that is not algorithmic. **It is evaluative.** A matching system's output cannot be scored without ground truth, and a live network furnishes none: an unmade match leaves no trace, so recall is unmeasurable — and a system that proposes everything scores perfectly.

This repository supplies the missing ground truth.

## What is here

| | |
|---|---|
| `generator/simgen.py` | Builds a corpus **answer-key first**. Deterministic: same seed, same corpus, any machine. |
| `corpora/corpus-a.sql` | 400 simulated members across countries, languages and time zones. Seed 20260919. |
| `corpora/corpus-b.sql` | 400 members, with offers that are blocked until an earlier link completes. |
| `schema/01_schema.sql` | The schema the corpora load into, and the two views a matcher reads. |
| `measure/02_measure.sql` | Recall, fabrication rate, chain-only performance, and precision at one against chance. |

## The three ideas

**Plant the answers before the distractors exist.** The tempting order is to invent four hundred plausible people, run a matcher, and read what it says. That produces a demo, not a measurement — the output always reads well, and there is no way to tell a real find from a fluent one. So the generator works backwards. It decides which need will be answered by which offer, and through whom, records those decisions, and only then emits the corpus that makes them true. Every subsequent offer is checked against the reservation and refused if it would satisfy a planted need by accident.

**Reserve needs that cannot be answered.** A fraction of needs are constructed so that nothing in the corpus can meet them — not directly, not through any chain. They are reserved *before a single offer exists*, which is the only ordering under which the guarantee holds.

This is the part that matters. Without a population of needs that genuinely cannot be met, **a matcher that invents answers is invisible**, because every answer looks like an answer. With them, the fabrication rate is directly observable at no annotation cost and with no judgement call. Read that number before you read recall.

**Measure ranking against chance, not against zero.** Recall says the answer was found. It says nothing about whether a member sees it, and nobody reads a list of five. So precision at one is compared to the baseline each need's own candidate count implies: four candidates means arbitrary ordering wins a quarter of the time. A matcher that beats chance only on needs with two candidates has not beaten chance.

One more property is engineered rather than hoped for: **a chain only matters when no direct answer exists.** In a dense corpus every need has a local offer, the shortest route always wins, and the multi-hop machinery never runs even though it is switched on. So concepts used in chain plants are deliberately withheld from the noise in the countries where those needs live. Density is the enemy of this test.

## Running it

```
psql "$DSN" -f schema/01_schema.sql
psql "$DSN" -f corpora/corpus-a.sql
# ... run your matcher, writing its output to sim.suggestions ...
psql "$DSN" -f measure/02_measure.sql
```

Your matcher reads `sim.v_match_needs` and `sim.v_match_offers`, and writes a row per suggestion into `sim.suggestions` with the chain it proposes and, if it ranks, `rank_in_need`. The measurement grades whatever it finds there. Nothing else is assumed about it.

To generate a fresh corpus at a different size or seed:

```
python3 generator/simgen.py --print-sql --members 400 --seed 20260919 > corpus.sql
```

## A reported baseline

Our own deterministic matcher, on these two corpora:

| Measure | Result |
|---|---|
| Recall of planted answers | **100%** |
| Proposed against 40 unanswerable controls | **0** |
| Chain-only opportunities ranked first | **20 of 20** |
| Precision at one | **44.0%**, against a chance baseline of **41.1%** |

The last row is the honest one. Ranking is barely better than arbitrary, and tracing it rather than assuming gave the finding that makes this benchmark worth publishing: **twenty-two of twenty-five cross-border cases have a tie at the very top, averaging 4.64 candidates identical on every signal a simulation can contain.** The signals that would break those ties are behavioural — standing earned in prior exchanges, recency, prior acceptances — and no simulation can produce them.

That is a clean statement of where synthetic evaluation ends and field data must begin. It is also the reason a ceiling exists here that no amount of algorithm work will lift.

## What is deliberately not here

The matcher is not in this repository, and neither are its ranking weights or the admission gates that sit in front of it. Those are the product.

This is a benchmark release, which means the dataset and the metric are published and the score is reported. That is the normal bargain — nobody publishing an evaluation set is expected to hand over the model with it — but it has a real cost and this README would rather state it than let you discover it: **you cannot reproduce our four numbers from this repository alone.**

What you can do is verify that the corpus construction is sound, verify that the controls are genuinely unanswerable, and grade your own matcher on identical ground. If you find a flaw in the construction, that finding is more valuable to us than the numbers were.

## Provenance and licence

Generated by The Good Machine, a global cooperative operated by Selah Now, LLC. The corpora contain no real people: participants are invented, handles rather than names, with no email address and no route to membership.

Licensed under the Apache License 2.0. See `LICENSE`. Copyright 2026 Selah Now, LLC.

The results above were measured on 20 September 2026.
