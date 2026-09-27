#!/usr/bin/env python3
"""Verify this benchmark before you trust a number it produces.

Takes one argument: a PostgreSQL connection string.

Everything here rests on one claim: that the control needs genuinely cannot be
answered by anything in the corpus. If that is false, the fabrication rate is
meaningless and so is every result reported against it.

So do not take it on faith. This checks it, and checks the isolation property
too, against a real PostgreSQL holding the loaded corpora.

    python3 verify.py "$DSN"

Run it after loading the schema and at least one corpus.
"""
import sys

try:
    import psycopg
except ImportError:
    sys.exit('needs psycopg:  pip install "psycopg[binary]"')

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


@check('the controls are genuinely unanswerable, corpus by corpus')
def _(c):
    """THE CHECK THAT MATTERS.

    A control need must have no active offer sharing its concept -- IN THE
    SAME CORPUS. Comparing across corpora is meaningless and will report a
    large number: two corpora loaded side by side share concept vocabulary by
    design, and an offer in corpus B says nothing about a control in corpus A.
    Getting that wrong was the first result this script produced.
    """
    rows = c.execute("""
        SELECT r.label,
               count(*) FILTER (WHERE o.sim_offer_id IS NOT NULL)
          FROM sim.planted p
          JOIN sim.runs  r ON r.run_id = p.run_id
          JOIN sim.needs n ON n.sim_need_id = p.sim_need_id
          LEFT JOIN sim.offers o ON o.run_id = p.run_id
                                AND o.concept = n.concept
                                AND o.active
         WHERE p.kind = 'unanswerable'
         GROUP BY r.label ORDER BY r.label
    """).fetchall()
    assert rows, 'no corpus is loaded'
    bad = [f'{label}: {n}' for label, n in rows if n]
    assert not bad, 'a control need CAN be answered in: ' + '; '.join(bad)
    return f'{len(rows)} corpora, no answerable control in any of them'


@check('every control need actually carries a concept')
def _(c):
    total, named = c.execute("""
        SELECT count(*), count(n.concept)
          FROM sim.planted p JOIN sim.needs n ON n.sim_need_id = p.sim_need_id
         WHERE p.kind = 'unanswerable'
    """).fetchone()
    assert total and total == named, \
        f'{total - named} of {total} controls have no concept to be matched on'
    return f'{total} controls, all named'


@check('nothing in the sandbox reaches outside it')
def _(c):
    n = c.execute("""
        SELECT count(*) FROM information_schema.table_constraints tc
          JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.constraint_schema = tc.constraint_schema
         WHERE tc.constraint_schema = 'sim'
           AND tc.constraint_type = 'FOREIGN KEY'
           AND ccu.table_schema <> 'sim'
    """).fetchone()[0]
    assert n == 0, f'{n} foreign keys leave schema sim'
    return 'no foreign key leaves schema sim'


@check('every plant is anchored to a need that exists')
def _(c):
    n = c.execute("""
        SELECT count(*) FROM sim.planted p
         WHERE NOT EXISTS (SELECT 1 FROM sim.needs n
                            WHERE n.sim_need_id = p.sim_need_id)
    """).fetchone()[0]
    assert n == 0, f'{n} plants point at a need that is not in the corpus'
    return 'every plant resolves'


@check('a chain plant really needs its chain')
def _(c):
    """A hop or chain_only plant claims no direct answer exists. If one offer
    could satisfy it outright, the plant is mislabelled and the chain result
    is inflated.

    TWO THINGS MAKE THIS EASY TO GET WRONG, and the first version of this
    check got both of them wrong and reported a thousand false failures.

      1. Geography. The generator withholds a plant's concept from the noise
         IN THE COUNTRY WHERE THE NEED LIVES. A same-concept offer elsewhere
         is not a shortcut unless both sides are remote-capable.

      2. The plant's own links. A chain's own offers share the concept by
         construction -- that is what makes them the answer. Counting them as
         shortcuts flags every correctly built chain in the corpus.
    """
    rows = c.execute("""
        SELECT r.label, count(*)
          FROM sim.planted p
          JOIN sim.runs    r  ON r.run_id = p.run_id
          JOIN sim.needs   n  ON n.sim_need_id = p.sim_need_id
          JOIN sim.members nm ON nm.sim_member_id = n.sim_member_id
          JOIN sim.offers  o  ON o.run_id = p.run_id
                             AND o.concept = n.concept
                             AND o.active
                             AND o.blocked_on IS NULL
          JOIN sim.members om ON om.sim_member_id = o.sim_member_id
         WHERE p.kind IN ('hop2', 'hop3', 'chain_only')
           -- it can only be a shortcut if it could actually reach the need
           AND (om.country = nm.country OR (o.remote_ok AND n.remote_ok))
           -- and if it is not one of the chain's own links
           AND o.sim_offer_id::text NOT IN (
                 SELECT l->>'offer_id' FROM jsonb_array_elements(p.chain) l)
         GROUP BY r.label
    """).fetchall()
    bad = [f'{label}: {n}' for label, n in rows if n]
    assert not bad, 'chain plants with a reachable direct answer: ' + '; '.join(bad)
    return 'no chain plant has a reachable shortcut'


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    failed = 0
    with psycopg.connect(sys.argv[1], autocommit=True) as conn:
        for name, fn in CHECKS:
            try:
                detail = fn(conn)
                print(f'  ok    {name}\n          {detail}')
            except AssertionError as e:
                failed += 1
                print(f'  FAIL  {name}\n          {e}')
    if failed:
        print(f'\n{failed} of {len(CHECKS)} FAILED. '
              'Do not report a score from this corpus until it passes.')
        sys.exit(1)
    print(f'\nall {len(CHECKS)} checks passed. The ground truth is sound.')


if __name__ == '__main__':
    main()
