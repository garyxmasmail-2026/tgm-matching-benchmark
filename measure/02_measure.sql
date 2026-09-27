-- The measurement. Run this after your matcher has written to
-- sim.suggestions, and it will tell you four things.
--
-- These are the only numbers this benchmark reports, and the fourth is the
-- one that matters most, because it is the one a matcher cannot fake.

-- ── 1 · RECALL ───────────────────────────────────────────────────────────────
-- Of the answers planted in the corpus, how many did the matcher find? The key
-- is exact rather than annotated: a suggestion matches a plant when its set of
-- offer ids is identical, so there is no partial credit and no judgement call.
CREATE OR REPLACE VIEW sim.v_recall AS
WITH plant AS (
  SELECT p.run_id, p.sim_need_id,
         (SELECT array_agg(x ORDER BY x)
            FROM (SELECT l->>'offer_id' AS x
                    FROM jsonb_array_elements(p.chain) l) q) AS offers
    FROM sim.planted p
   WHERE p.kind <> 'unanswerable'
),
said AS (
  SELECT s.run_id, s.trial, s.sim_need_id,
         (SELECT array_agg(x ORDER BY x)
            FROM (SELECT l->>'offer_id' AS x
                    FROM jsonb_array_elements(s.chain) l) q) AS offers
    FROM sim.suggestions s
)
SELECT pk.run_id, sd.trial,
       count(DISTINCT pk.sim_need_id)                       AS planted,
       count(DISTINCT pk.sim_need_id)
         FILTER (WHERE sd.offers = pk.offers)               AS found
  FROM plant pk
  LEFT JOIN said sd ON sd.run_id = pk.run_id
                   AND sd.sim_need_id = pk.sim_need_id
 GROUP BY pk.run_id, sd.trial;

-- ── 2 · FABRICATION ──────────────────────────────────────────────────────────
-- The number to read FIRST. A control need has no answer anywhere in the
-- corpus -- not directly, not through any chain -- and the generator reserves
-- them before a single offer exists, which is the only ordering under which
-- that guarantee holds. So every suggestion counted here is an invention, by
-- construction, with nothing to argue about.
--
-- A matcher that proposes everything scores perfectly on recall. This is the
-- number that catches it.
CREATE OR REPLACE VIEW sim.v_invented AS
SELECT p.run_id, s.trial,
       count(*) FILTER (WHERE p.kind = 'unanswerable')      AS controls,
       count(s.sim_suggestion_id)                           AS invented
  FROM sim.planted p
  LEFT JOIN sim.suggestions s ON s.run_id = p.run_id
                            AND s.sim_need_id = p.sim_need_id
 WHERE p.kind = 'unanswerable'
 GROUP BY p.run_id, s.trial;

-- ── 3 · THE CHAINS, WHICH ARE THE POINT ──────────────────────────────────────
-- A chain plant can be satisfied ONLY through an intermediary: the generator
-- withheld every direct answer in that country. Finding them is the whole
-- reason a system like this is worth building, so they are counted on their
-- own rather than averaged into the rest.
--
-- THREE KINDS COUNT AS CHAINS, and which ones a corpus contains varies:
--   hop2, hop3   present in every corpus
--   chain_only   only in corpora that model a blocked offer -- one where the
--                person who could help is themselves waiting on someone else
--
-- The first version of this view filtered on chain_only alone and therefore
-- reported nothing at all against corpus-a, which has none. A measurement
-- that silently returns zero rows is worse than one that fails, so the kind
-- is broken out rather than collapsed.
CREATE OR REPLACE VIEW sim.v_chain_only AS
SELECT p.run_id, s.trial, p.kind,
       count(DISTINCT p.sim_need_id)                        AS chains,
       count(DISTINCT p.sim_need_id)
         FILTER (WHERE s.rank_in_need = 1)                  AS ranked_first
  FROM sim.planted p
  LEFT JOIN sim.suggestions s ON s.run_id = p.run_id
                            AND s.sim_need_id = p.sim_need_id
 WHERE p.kind IN ('hop2', 'hop3', 'chain_only')
 GROUP BY p.run_id, s.trial, p.kind;

-- ── 4 · PRECISION AT ONE, AGAINST CHANCE ─────────────────────────────────────
-- Recall says the answer was found. It says nothing about whether a member
-- SEES it, and nobody reads a list of five.
--
-- The comparison that makes this honest is the chance baseline. If a need drew
-- four candidates, arbitrary ordering puts the right one first a quarter of the
-- time. Averaging 1/N across the found plants gives the score to beat, and a
-- matcher that beats it only on needs with two candidates has not beaten it.
--
-- Report both numbers or neither.
CREATE OR REPLACE VIEW sim.v_precision AS
WITH plant AS (
  SELECT p.run_id, p.sim_need_id, p.kind,
         (SELECT array_agg(x ORDER BY x)
            FROM (SELECT l->>'offer_id' AS x
                    FROM jsonb_array_elements(p.chain) l) q) AS offers
    FROM sim.planted p
   WHERE p.kind <> 'unanswerable'
),
said AS (
  SELECT s.run_id, s.trial, s.sim_need_id, s.sim_suggestion_id, s.rank_in_need,
         (SELECT array_agg(x ORDER BY x)
            FROM (SELECT l->>'offer_id' AS x
                    FROM jsonb_array_elements(s.chain) l) q) AS offers
    FROM sim.suggestions s
)
SELECT pk.run_id, sd.trial, pk.kind, pk.sim_need_id,
       count(sd.sim_suggestion_id)                          AS candidates,
       min(sd.rank_in_need) FILTER (WHERE sd.offers = pk.offers)
                                                            AS right_answer_at,
       1.0 / NULLIF(count(sd.sim_suggestion_id), 0)         AS chance_of_first
  FROM plant pk
  JOIN said sd ON sd.run_id = pk.run_id AND sd.sim_need_id = pk.sim_need_id
 GROUP BY pk.run_id, sd.trial, pk.kind, pk.sim_need_id;


-- ── THE SCORECARD ────────────────────────────────────────────────────────────
-- One row. Run it and report what it says, including the last two columns.
SELECT r.trial,
       r.planted, r.found,
       round(100.0 * r.found / NULLIF(r.planted, 0), 1)     AS recall_pct,
       i.controls, i.invented,
       sum(c.chains)                                        AS chains,
       sum(c.ranked_first)                                  AS chains_first,
       count(*) FILTER (WHERE p.right_answer_at = 1)        AS first_place,
       round(100.0 * count(*) FILTER (WHERE p.right_answer_at = 1)
             / NULLIF(count(*) FILTER (WHERE p.right_answer_at IS NOT NULL), 0),
             1)                                             AS precision_at_1_pct,
       round(100.0 * avg(p.chance_of_first)
             FILTER (WHERE p.right_answer_at IS NOT NULL), 1)
                                                            AS chance_pct
  FROM sim.v_recall r
  LEFT JOIN sim.v_invented   i ON i.run_id = r.run_id AND i.trial = r.trial
  LEFT JOIN sim.v_chain_only c ON c.run_id = r.run_id AND c.trial = r.trial
  LEFT JOIN sim.v_precision  p ON p.run_id = r.run_id AND p.trial = r.trial
 GROUP BY r.trial, r.planted, r.found, i.controls, i.invented;
