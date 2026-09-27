# A small benchmark for multi-hop matching in mutual-credit networks

We are building a cooperative where members help each other across countries, and we needed a way to check whether our matching was actually any good. We couldn't find one, so we made a simple one. We're sharing it in case it is useful to others working on timebanks, mutual-credit networks or community exchange, and because we would like to be corrected where we have got it wrong.

## Why we made it

Most timebanks and mutual-credit networks match one person's need with one person's offer. Some of the most helpful exchanges are harder to see: a chain of three or four people where the first never meets the last, or a need in one country that someone in another country could meet.

A computer can look for those. The hard part, for us, was knowing whether it had found the right ones. In a live network you only see the matches that were made. You can't see the ones that were missed, and a system that suggests everything can look better than it is.

So we tried to build a test with the answers written down in advance.

## What is here

| | |
|---|---|
| `generator/simgen.py` | Builds a simulated community, starting from the answer key. The same seed gives the same corpus on any machine. |
| `corpora/corpus-a.sql` | 400 simulated members across countries, languages and time zones. Seed 20260919. |
| `corpora/corpus-b.sql` | 400 members, where some offers only become available after an earlier exchange happens. |
| `schema/01_schema.sql` | The tables the corpora load into, and the two views a matcher reads from. |
| `measure/02_measure.sql` | Scores a matcher: how many planted answers it found, whether it suggested anything for needs that have no answer, how it did on chains, and how its first choice compares with picking at random. |
| `verify.py` | Checks the corpus itself, so you don't have to take our word that it was built correctly. |

## How it works

**The answers come first.** The generator decides ahead of time which need will be met by which offer, and through whom. It writes those decisions down, then builds the rest of the community around them, and refuses any extra offer that would answer a planted need by accident.

**Some needs have no answer at all.** Before any offers exist, a share of needs is set aside so that nothing in the corpus can meet them, directly or through a chain. If a matcher suggests something for one of these, it has made something up. We found this the most useful number to look at, and we'd suggest looking at it before recall.

**First choices are compared with chance.** Finding the right answer somewhere in a list is not the same as putting it first. So the score for a matcher's first choice is compared with what random ordering would get, given how many candidates each need had.

**Chains are only needed where nothing closer exists.** If every need had a local answer, a matcher would never need to look further. So in a few places we held back local offers on purpose, to see whether a longer chain gets found.

## Running it

```
psql "$DSN" -f schema/01_schema.sql
psql "$DSN" -f corpora/corpus-a.sql
python3 verify.py "$DSN"
# ... run your matcher, writing its output to sim.suggestions ...
psql "$DSN" -f measure/02_measure.sql
```

Your matcher reads `sim.v_match_needs` and `sim.v_match_offers`, and writes one row per suggestion into `sim.suggestions`, with the chain it proposes and, if it ranks them, `rank_in_need`.

To generate a corpus at a different size or seed:

```
python3 generator/simgen.py --print-sql --members 400 --seed 20260919 > corpus.sql
```

## How our own matcher did

These are the results from our own early matcher on these two corpora, measured on 20 September 2026:

| Measure | Result |
|---|---|
| Planted answers found | 100% |
| Suggestions made for the 40 needs with no answer | 0 |
| Chain-only cases where the chain was ranked first | 20 of 20 |
| First choice correct | 44.0%, against 41.1% by chance |

The last line matters most, and it isn't good. Our ranking is only a little better than random. When we looked into why, we found that in 22 of the 25 cross-border cases, several candidates (4.64 on average) were tied at the top on every signal a simulation can hold. What would separate them is how people actually behave over time: their record in past exchanges, how recently they've been active, what they have accepted before. A simulation can't produce that. We think this is where synthetic testing runs out and real use has to take over, but we could be wrong, and we'd welcome other views.

## What isn't included

Our matcher, its ranking weights and the checks it runs before suggesting a match are not in this repository. That means you can't reproduce our four numbers from this repository alone, and we'd rather say so plainly.

What you can do is check that the corpora are built soundly, check that the unanswerable needs really can't be answered, and test your own matcher against the same data. If you find a flaw in how any of this was built, please open an issue. That would help us more than anything else.

## Where it comes from

Made by The Good Machine, a cooperative operated by Selah Now, LLC. The corpora contain no real people. Every participant is invented, identified by a handle rather than a name, with no email address and no link to real membership.

Licensed under the Apache License 2.0. See `LICENSE`. Copyright 2026 Selah Now, LLC.
