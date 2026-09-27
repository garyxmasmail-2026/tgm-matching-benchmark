-- © 2024–2026 Gary Christmas / Selah Now LLC.
-- S1 · A place to simulate matching, and one contract the matcher reads.
--
-- NOT EXECUTED BEFORE DELIVERY. One transaction; the readiness query at the
-- end reports what the database holds rather than what was intended.
--
-- ─────────────────────────────────────────────────────────────────────────
-- WHY A SEPARATE SCHEMA AND NOT A FLAG ON THE REAL TABLES
--
--   The obvious way to stage this is to admit fifty invented people and see
--   what the matcher does with them. It is also the expensive one and the one
--   that cannot be undone.
--
--   A real applicant costs an entry conversation, two scorers, a deep research
--   call, several emails, a council ballot, a member row, a founding grant, a
--   Stellar credential — and a salted record hash that goes to Arweave. That
--   last step is permanent by design. Inventing people and anchoring them
--   would put fiction into the one record whose entire worth is that it is not
--   fiction, and no later correction takes it back off the chain.
--
--   A boolean column would not save it either. A flag has to be honoured
--   everywhere — the reconciler, the founding-member count, the commitment
--   tree, every disclosure — and the first place that forgets is the place it
--   leaks. Nothing in this project reads a flag it was never told about.
--
--   So: a separate schema, and no foreign key from any of it into public.
--   Simulated members cannot be voted on, cannot be issued GOOD, cannot enter
--   the commitment tree and cannot be anchored, because the columns that would
--   carry them there do not exist here. The isolation is structural. It does
--   not depend on anybody remembering.
--
-- ─────────────────────────────────────────────────────────────────────────
-- WHY THE CONTRACT VIEWS ARE IN THIS FILE TOO
--
--   A simulator is only worth building if the thing it exercises is the thing
--   that will run in production. If the matcher reads sim tables directly, it
--   will be written to read sim tables, and the day it points at real members
--   is the day it is tested for the first time.
--
--   So both sides publish the same six-and-a-bit columns under the same names:
--     public.v_match_needs   / public.v_match_offers    — real members
--     sim.v_match_needs      / sim.v_match_offers       — invented ones
--
--   The matcher takes a schema name and nothing else. It cannot tell the
--   difference, which is the point: whatever the simulation proves, it proves
--   about the code that will run for real.
--
--   public.v_match_* are deliberately NOT the directory views. The directory
--   decides what a member may SEE; matching decides what may be CONSIDERED.
--   A member who keeps their profile private is still owed a match — they
--   simply are not named in one. Collapsing those two questions into one view
--   would quietly make privacy cost you help, and that trade is not ours to
--   make on someone's behalf.
--
-- ─────────────────────────────────────────────────────────────────────────
-- READ THIS BEFORE ADDING ANYTHING
--   Nothing in schema sim is fingerprinted, anchored, counted, or published.
--   If a future change gives it a a record fingerprint, a member_id that references
--   the production members table, or a row in the chain operation queue, that change has defeated the
--   purpose of the file and should be rejected on sight.

BEGIN;

CREATE SCHEMA IF NOT EXISTS sim;

COMMENT ON SCHEMA sim IS
  'Simulated members, needs and offers for exercising the matcher. No foreign key reaches public from here, nothing is fingerprinted, and nothing may ever be anchored. If anything in this schema acquires a a record fingerprint it has stopped doing its job.';


-- ══ 1 · A RUN ═══════════════════════════════════════════════════════════════
-- Every corpus is a run, so several can exist at once and any one of them can
-- be thrown away whole. A simulation you cannot delete is a simulation you
-- stop trusting, because you can no longer say which numbers came from where.
CREATE TABLE IF NOT EXISTS sim.runs (
  run_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label       text NOT NULL,

  -- The seed the generator was given. Written down because "it worked when I
  -- ran it" is not a result anyone can check. Same seed, same corpus, same
  -- score, on any machine.
  seed        bigint NOT NULL,

  -- What was asked for: counts, countries, the intended mix of match classes.
  -- Kept as given rather than as achieved; sim.v_run_shape reports what the
  -- data actually came out as, and the two disagreeing is a finding.
  spec        jsonb NOT NULL DEFAULT '{}'::jsonb,

  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sim_run_spec_is_an_object CHECK (jsonb_typeof(spec) = 'object')
);

COMMENT ON TABLE sim.runs IS
  'One generated corpus. The seed is recorded so the corpus can be rebuilt exactly; the spec is what was asked for, which is not always what was produced.';


-- ══ 2 · INVENTED PEOPLE ═════════════════════════════════════════════════════
-- Deliberately thin. A simulated member needs only what matching reads:
-- where they are, what they speak, and nothing else. No email, no name that
-- could be mistaken for a person's, no status, no role, no grant.
CREATE TABLE IF NOT EXISTS sim.members (
  sim_member_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        uuid NOT NULL REFERENCES sim.runs(run_id) ON DELETE CASCADE,

  -- A label, not a name: 'US-014'. Anything that reads like a real person's
  -- name invites someone to treat a row here as a row about somebody.
  handle        text NOT NULL,

  country       text NOT NULL CHECK (country ~ '^[A-Z]{2}$'),
  region        text,
  timezone      text,
  languages     text[] NOT NULL DEFAULT '{}',

  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, handle)
);

CREATE INDEX IF NOT EXISTS sim_members_run_idx ON sim.members (run_id, country);

COMMENT ON TABLE sim.members IS
  'Invented participants. Handles, not names. No email and no path to membership: this table cannot reach the production members table and must never be given a way to.';


-- ══ 3 · WHAT THEY ASK FOR AND WHAT THEY CAN DO ══════════════════════════════
-- Same columns as the real member_needs / member_offers as far as matching is
-- concerned, and nothing beyond that. Where production says `active` and
-- `met_at`, so does this, because the matcher will filter on them.
CREATE TABLE IF NOT EXISTS sim.needs (
  sim_need_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        uuid NOT NULL REFERENCES sim.runs(run_id) ON DELETE CASCADE,
  sim_member_id uuid NOT NULL REFERENCES sim.members(sim_member_id) ON DELETE CASCADE,

  title       text NOT NULL,
  detail      text,
  category    text,
  concept     text,
  language    text,
  remote_ok   boolean NOT NULL DEFAULT false,
  urgency     text CHECK (urgency IS NULL OR urgency IN ('whenever','soon','urgent')),
  quantity    numeric(12,2),
  unit        text,

  active      boolean NOT NULL DEFAULT true,
  matchable   boolean NOT NULL DEFAULT true,
  met_at      timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sim.offers (
  sim_offer_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        uuid NOT NULL REFERENCES sim.runs(run_id) ON DELETE CASCADE,
  sim_member_id uuid NOT NULL REFERENCES sim.members(sim_member_id) ON DELETE CASCADE,

  title       text NOT NULL,
  detail      text,
  category    text,
  concept     text,
  language    text,
  remote_ok   boolean NOT NULL DEFAULT false,
  quantity    numeric(12,2),
  unit        text,

  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sim_needs_run_idx  ON sim.needs  (run_id, concept) WHERE active;
CREATE INDEX IF NOT EXISTS sim_offers_run_idx ON sim.offers (run_id, concept) WHERE active;


-- ══ 4 · THE ANSWER KEY ══════════════════════════════════════════════════════
--
-- THIS IS THE REASON THE FILE EXISTS.
--
--   Generating plausible members and hoping matches emerge produces a corpus
--   nobody can be graded against. The matcher returns something, the something
--   reads well, and there is no way to tell a good suggestion from a fluent
--   one. That is exactly the failure mode worth engineering against, and it
--   cannot be caught by looking at output.
--
--   So the chains are decided FIRST. The generator picks which need will be
--   answered by which offer, and through whom, and only then writes the needs
--   and offers that realise those decisions — and then buries them in traffic.
--   Every row here is a claim the data is required to support, and
--   sim.v_plant_integrity checks that it does.
--
-- HOPS 0 IS THE MOST IMPORTANT CLASS IN THIS TABLE
--   A planted need with no chain is a need with no answer, on purpose. It is
--   the control. A matcher that returns a confident suggestion for one of
--   these is not matching, it is composing — and without a population of
--   needs that genuinely cannot be met, that failure is invisible, because
--   every answer looks like an answer.
CREATE TABLE IF NOT EXISTS sim.planted (
  plant_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      uuid NOT NULL REFERENCES sim.runs(run_id) ON DELETE CASCADE,

  kind text NOT NULL CHECK (kind IN (
    'direct',        -- one offer, same country, meets it outright
    'cross_border',  -- the only answer is in another country, and travels
    'hop2',          -- A is answered only because B is answered first
    'hop3',          -- three links, and no pair of them is a match on its own
    'pool',          -- several offers combine into one nobody could give alone
    'unanswerable'   -- THE CONTROL. Nothing here can meet this. hops = 0.
  )),

  hops integer NOT NULL CHECK (hops >= 0),

  -- The need this claim is about. Every plant is anchored to one need, so a
  -- matcher's output can be scored need by need.
  sim_need_id uuid NOT NULL REFERENCES sim.needs(sim_need_id) ON DELETE CASCADE,

  -- The chain, in order: [{"need_id": "...", "offer_id": "..."}, ...].
  -- Empty for 'unanswerable', which is why the constraint below is written
  -- the way it is rather than simply demanding a non-empty array.
  chain jsonb NOT NULL DEFAULT '[]'::jsonb,

  -- Why this was planted, in the generator's words. A plant nobody can read
  -- later is a number without an argument.
  note text,

  created_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sim_plant_chain_is_a_list CHECK (jsonb_typeof(chain) = 'array'),
  -- hops and the chain must agree, in both directions. An 'unanswerable' with
  -- a chain is a contradiction; so is a 'hop3' with nothing in it.
  CONSTRAINT sim_plant_hops_match_chain
    CHECK (jsonb_array_length(chain) = hops),
  CONSTRAINT sim_plant_unanswerable_is_empty
    CHECK ((kind = 'unanswerable') = (hops = 0))
);

CREATE INDEX IF NOT EXISTS sim_planted_run_idx  ON sim.planted (run_id, kind);
CREATE INDEX IF NOT EXISTS sim_planted_need_idx ON sim.planted (sim_need_id);

COMMENT ON TABLE sim.planted IS
  'The answer key, written before the data that realises it. kind = unanswerable with hops = 0 is the control group: needs nothing in the corpus can meet, so that a matcher which invents answers can be caught doing it.';


-- ══ 5 · WHAT A MATCHER PROPOSED ═════════════════════════════════════════════
-- The same shape as public.suggestions, kept separate for the same reason
-- everything else here is: a simulated suggestion is not part of the record of
-- what this cooperative actually proposed to anybody.
CREATE TABLE IF NOT EXISTS sim.suggestions (
  sim_suggestion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id      uuid NOT NULL REFERENCES sim.runs(run_id) ON DELETE CASCADE,

  -- Which attempt produced it. Two methods scored against one corpus is the
  -- comparison worth having, so the corpus and the attempt are separate keys.
  trial       text NOT NULL,
  method      text,

  kind        text NOT NULL,
  hops        integer NOT NULL DEFAULT 1 CHECK (hops >= 1),
  sim_need_id uuid NOT NULL REFERENCES sim.needs(sim_need_id) ON DELETE CASCADE,
  chain       jsonb NOT NULL DEFAULT '[]'::jsonb,
  rationale   text,
  confidence  numeric(4,3) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  created_at  timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT sim_suggestion_chain_is_a_list CHECK (jsonb_typeof(chain) = 'array')
);

CREATE INDEX IF NOT EXISTS sim_suggestions_trial_idx ON sim.suggestions (run_id, trial);


-- ══ 6 · THE CONTRACT ════════════════════════════════════════════════════════
-- Six columns of substance and a few of context, identical on both sides.
-- The matcher is handed a schema name and reads these. It never names a table.

-- [removed for publication: the production-side half of the match contract.
--  The sim-side views below are the benchmark interface and are complete.]
-- [removed for publication: the production-side half of the match contract.
--  The sim-side views below are the benchmark interface and are complete.]
CREATE OR REPLACE VIEW sim.v_match_needs AS
SELECT n.sim_need_id                      AS need_id,
       n.sim_member_id                    AS member_id,
       COALESCE(n.concept, n.category)    AS match_key,
       n.category, n.language, n.remote_ok, n.urgency,
       n.quantity, n.unit,
       m.country, m.region, m.languages,
       n.title, n.detail, n.created_at,
       n.run_id
  FROM sim.needs n
  JOIN sim.members m ON m.sim_member_id = n.sim_member_id
 WHERE n.active AND n.matchable AND n.met_at IS NULL;

CREATE OR REPLACE VIEW sim.v_match_offers AS
SELECT o.sim_offer_id                     AS offer_id,
       o.sim_member_id                    AS member_id,
       COALESCE(o.concept, o.category)    AS match_key,
       o.category, o.language, o.remote_ok,
       o.quantity, o.unit,
       m.country, m.region, m.languages,
       o.title, o.detail, o.created_at,
       o.run_id
  FROM sim.offers o
  JOIN sim.members m ON m.sim_member_id = o.sim_member_id
 WHERE o.active;


-- ══ 7 · IS THE ANSWER KEY TRUE? ═════════════════════════════════════════════
-- A planted chain naming an offer that does not exist, or that the matcher
-- could never reach through the contract views, is a wrong answer in the
-- marking scheme. Every score computed against it would be wrong and would
-- look fine. So the key is checked before anything is graded against it.
CREATE OR REPLACE VIEW sim.v_plant_integrity AS
WITH links AS (
  SELECT p.plant_id, p.run_id, p.kind, p.hops,
         (l->>'need_id')::uuid  AS need_id,
         (l->>'offer_id')::uuid AS offer_id
    FROM sim.planted p
    CROSS JOIN LATERAL jsonb_array_elements(p.chain) AS l
),
checked AS (
  SELECT l.plant_id, l.run_id, l.kind,
         count(*)                                                  AS links,
         count(*) FILTER (WHERE vn.need_id  IS NULL)                AS need_unreachable,
         count(*) FILTER (WHERE vo.offer_id IS NULL)                AS offer_unreachable,
         count(*) FILTER (WHERE vn.match_key IS DISTINCT FROM vo.match_key) AS key_mismatch
    FROM links l
    LEFT JOIN sim.v_match_needs  vn ON vn.need_id  = l.need_id
    LEFT JOIN sim.v_match_offers vo ON vo.offer_id = l.offer_id
   GROUP BY l.plant_id, l.run_id, l.kind
)
SELECT run_id, kind,
       count(*)                                            AS plants,
       sum(links)                                           AS links,
       sum(need_unreachable)                                AS links_whose_need_is_unreachable,
       sum(offer_unreachable)                               AS links_whose_offer_is_unreachable,
       sum(key_mismatch)                                    AS links_that_do_not_actually_match,
       CASE WHEN sum(need_unreachable) + sum(offer_unreachable) + sum(key_mismatch) = 0
            THEN 'sound' ELSE '*** THE ANSWER KEY IS WRONG ***' END AS verdict
  FROM checked
 GROUP BY run_id, kind;

COMMENT ON VIEW sim.v_plant_integrity IS
  'Whether the answer key is supported by the data. Anything other than "sound" means scores computed against this run are meaningless, and it must be read before they are believed.';


-- ══ 8 · THE SHAPE THAT WAS ACTUALLY PRODUCED ════════════════════════════════
-- What the corpus came out as, against what the spec asked for. Generators
-- drift; a spec is an intention and this is the outcome.
CREATE OR REPLACE VIEW sim.v_run_shape AS
SELECT r.run_id, r.label, r.seed,
       (SELECT count(*) FROM sim.members m WHERE m.run_id = r.run_id) AS members,
       (SELECT count(DISTINCT m.country) FROM sim.members m WHERE m.run_id = r.run_id) AS countries,
       (SELECT count(*) FROM sim.needs  n WHERE n.run_id = r.run_id)  AS needs,
       (SELECT count(*) FROM sim.offers o WHERE o.run_id = r.run_id)  AS offers,
       (SELECT count(*) FROM sim.planted p WHERE p.run_id = r.run_id) AS plants,
       (SELECT count(*) FROM sim.planted p WHERE p.run_id = r.run_id AND p.kind = 'unanswerable') AS controls,
       (SELECT count(*) FROM sim.planted p WHERE p.run_id = r.run_id AND p.hops >= 2) AS multi_hop_plants
  FROM sim.runs r;


-- ══ 9 · THE SCORE ═══════════════════════════════════════════════════════════
--
-- A matcher writes into sim.suggestions under a trial name; this grades it.
--
-- FOUR NUMBERS, AND THE FOURTH IS THE ONE TO READ FIRST
--   found          — planted chains the matcher recovered
--   missed         — planted chains it did not
--   invented       — suggestions for needs planted as having NO answer
--   wrong_chain    — right need, wrong route
--
--   A system can score well on the first two and still be unusable, because
--   precision and recall over answerable needs say nothing about what it does
--   when there is nothing to say. `invented` is the honesty measure, and a
--   matcher with a high one should be rejected however good its recall.
CREATE OR REPLACE VIEW sim.v_score AS
WITH plants AS (
  SELECT p.run_id, p.plant_id, p.kind, p.hops, p.sim_need_id,
         -- Order-independent identity of a chain, so a route found by a
         -- different traversal still counts as the same route.
         (SELECT array_agg(x ORDER BY x)
            FROM (SELECT (l->>'offer_id') AS x
                    FROM jsonb_array_elements(p.chain) l) q) AS offer_set
    FROM sim.planted p
),
said AS (
  SELECT s.run_id, s.trial, s.sim_need_id, s.sim_suggestion_id,
         (SELECT array_agg(x ORDER BY x)
            FROM (SELECT (l->>'offer_id') AS x
                    FROM jsonb_array_elements(s.chain) l) q) AS offer_set
    FROM sim.suggestions s
),
trials AS (SELECT DISTINCT run_id, trial FROM sim.suggestions)
SELECT t.run_id, t.trial,
       count(*) FILTER (WHERE p.kind <> 'unanswerable')                        AS answerable_plants,
       count(*) FILTER (WHERE p.kind <> 'unanswerable' AND hit.plant_id IS NOT NULL)  AS found,
       count(*) FILTER (WHERE p.kind <> 'unanswerable' AND hit.plant_id IS NULL)      AS missed,
       count(*) FILTER (WHERE p.kind <> 'unanswerable'
                          AND hit.plant_id IS NULL AND anysaid.sim_need_id IS NOT NULL) AS wrong_chain,
       count(*) FILTER (WHERE p.kind = 'unanswerable' AND anysaid.sim_need_id IS NOT NULL) AS invented,
       count(*) FILTER (WHERE p.kind = 'unanswerable')                         AS controls,
       round(
         100.0 * count(*) FILTER (WHERE p.kind <> 'unanswerable' AND hit.plant_id IS NOT NULL)
         / NULLIF(count(*) FILTER (WHERE p.kind <> 'unanswerable'), 0), 1)     AS recall_pct
  FROM trials t
  JOIN plants p ON p.run_id = t.run_id
  -- did any suggestion in this trial recover this exact route?
  LEFT JOIN LATERAL (
    SELECT p.plant_id FROM said s
     WHERE s.run_id = t.run_id AND s.trial = t.trial
       AND s.sim_need_id = p.sim_need_id
       AND s.offer_set = p.offer_set
     LIMIT 1
  ) hit ON true
  -- did it say ANYTHING about this need? (separates a miss from a wrong turn,
  -- and is the whole test for the control group)
  LEFT JOIN LATERAL (
    SELECT s.sim_need_id FROM said s
     WHERE s.run_id = t.run_id AND s.trial = t.trial
       AND s.sim_need_id = p.sim_need_id
     LIMIT 1
  ) anysaid ON true
 GROUP BY t.run_id, t.trial;

COMMENT ON VIEW sim.v_score IS
  'How a trial did against the answer key. Read invented before recall: a matcher that answers needs planted as unanswerable is generating, and its recall is not evidence of anything.';

COMMIT;



-- ── where a matcher reports its ranking ────────────────────────
ALTER TABLE sim.suggestions ADD COLUMN IF NOT EXISTS rank_in_need integer;
ALTER TABLE sim.suggestions ADD COLUMN IF NOT EXISTS rank_score numeric(12,4);

COMMENT ON COLUMN sim.suggestions.rank_in_need IS
  'Position among the candidates for this need, 1 being what the member would be shown first. NULL means unranked, which is a different thing from ranked last: precision at one cannot be computed for a matcher that does not order its output, and the measurement will say so rather than guess.';

COMMENT ON COLUMN sim.suggestions.rank_score IS
  'Whatever your matcher scored this candidate. Recorded so a tie at the top is visible as a tie rather than as an arbitrary winner -- which is exactly the finding that made this benchmark worth publishing.';

-- ── readiness ────────────────────────────────────────
-- Run this after loading the schema. It reports what the database holds
-- rather than what this file intended, which is the only kind of readiness
-- check worth having.
SELECT
  (SELECT count(*) FROM information_schema.schemata
    WHERE schema_name = 'sim')                                      AS sim_schema,
  (SELECT count(*) FROM information_schema.tables
    WHERE table_schema = 'sim')                                     AS sim_tables,
  (SELECT count(*) FROM information_schema.views
    WHERE table_schema = 'sim')                                     AS sim_views,
  -- The isolation, asserted rather than described: no column anywhere in sim
  -- may reference anything outside it. This is the property that lets a
  -- corpus of four hundred invented people sit in the same database as a
  -- cooperative's real record without ever touching it.
  (SELECT count(*) FROM information_schema.table_constraints tc
     JOIN information_schema.constraint_column_usage ccu
       ON ccu.constraint_name = tc.constraint_name
      AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_schema = 'sim'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND ccu.table_schema <> 'sim')                                AS leaks_out,
  (SELECT count(*) FROM sim.runs)                                   AS corpora;
-- Expect 1 schema, 6 tables, 3 views, leaks_out = 0, and one row per corpus
-- loaded. If leaks_out is anything but zero the schema has grown a path out
-- of its sandbox and this file has stopped doing its job.
