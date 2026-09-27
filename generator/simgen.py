#!/usr/bin/env python3
"""Generate a simulated corpus of members, needs and offers — answer key first.

  python3 tools/simgen.py --dsn "$SIM_DSN" --members 400 --seed 20260919
  python3 tools/simgen.py --print-sql --members 40 --seed 1 > /tmp/corpus.sql

WHY THE ANSWER KEY COMES FIRST
  The tempting way round is to invent 400 plausible people, let the matcher
  loose, and read what it says. That produces a demo, not a measurement. The
  output always reads well — that is what these models are good at — and there
  is no way to tell a real find from a fluent one.

  So this does it backwards. It decides which need will be answered by which
  offer, and through whom, writes those decisions into sim.planted, and only
  then emits the needs and offers that make them true. Everything else in the
  corpus is noise generated around them.

  The corpus is then something a matcher can be GRADED against rather than
  admired on.

THE FOUR CLASSES, AND THE CONTROL
  direct        one offer, same country, meets it outright
  cross_border  the only answer is abroad; both sides are remote_ok
  hop2          A's need is met by B, who could only help because C met B's
  hop3          three links, no pair of which is a match on its own
  unanswerable  NOTHING in the corpus can meet it. hops = 0.

  The last class is the point of the exercise. Without a population of needs
  that genuinely cannot be met, a matcher that invents answers is invisible,
  because every answer looks like an answer. sim.v_score counts suggestions
  made against these as `invented`, and that number should be read before
  recall.

WHY MULTI-HOP NEEDS THE CORPUS TO BE SPARSE
  A chain only matters when no direct answer exists. In a dense corpus every
  need has a local offer, the shortest route always wins, and the multi-hop
  machinery is never exercised even though it runs. So the concepts used in
  hop plants are deliberately withheld from the noise in the countries where
  those needs live. Density is the enemy of this test, and it has to be
  engineered out rather than hoped away.

DETERMINISM
  Same seed, same corpus, on any machine. A score you cannot reproduce is an
  anecdote. The seed is written into sim.runs alongside the spec.

NOTHING HERE TOUCHES THE REAL TABLES
  Every statement targets schema sim. This script has no code path that writes
  to public, and S1's readiness query asserts that sim has no foreign key
  reaching into it.
"""

import argparse, json, random, sys, uuid

# ── the world ───────────────────────────────────────────────────────────────
# Countries carry a weight because a real cooperative is not uniform, and a
# matcher tuned on a flat distribution meets a lopsided one in production.
COUNTRIES = [
    ('US', 0.26, 'en', ['California', 'Michigan', 'Texas', 'New York', 'Oregon']),
    ('CA', 0.06, 'en', ['Ontario', 'British Columbia']),
    ('MX', 0.05, 'es', ['Jalisco', 'Oaxaca']),
    ('BR', 0.05, 'pt', ['Bahia', 'Sao Paulo']),
    ('GB', 0.07, 'en', ['West Country', 'Yorkshire']),
    ('IE', 0.03, 'en', ['West Cork', 'Connacht']),
    ('ES', 0.04, 'es', ['Andalucia', 'Galicia']),
    ('FR', 0.04, 'fr', ['Bretagne', 'Occitanie']),
    ('DE', 0.04, 'de', ['Bayern', 'Sachsen']),
    ('KE', 0.06, 'sw', ['Nairobi', 'Kisumu']),
    ('NG', 0.06, 'en', ['Lagos', 'Kano']),
    ('ZA', 0.04, 'en', ['Western Cape', 'Gauteng']),
    ('IN', 0.07, 'hi', ['Kerala', 'Maharashtra']),
    ('PH', 0.04, 'tl', ['Luzon', 'Visayas']),
    ('ID', 0.03, 'id', ['Java', 'Sulawesi']),
    ('AU', 0.03, 'en', ['Victoria', 'Queensland']),
    ('NZ', 0.02, 'en', ['Otago']),
    ('PL', 0.02, 'pl', ['Malopolska']),
    ('UA', 0.02, 'uk', ['Lviv']),
    ('CO', 0.03, 'es', ['Antioquia']),
]

# Concepts are the matching vocabulary. Phrasing is deliberately varied per
# concept so that a matcher leaning on string similarity rather than meaning
# gets no free marks: "school run" and "nursery pickup" are the same concept
# and share almost no characters.
CONCEPTS = {
    'childcare':      (['school run cover', 'nursery pickup', 'someone to watch the little ones'],
                       ['can collect kids after 3', 'free weekday mornings for childcare']),
    'elder_care':     (['checking in on my mother', 'company for an older neighbour'],
                       ['can sit with someone twice a week', 'happy to visit the housebound']),
    'transport':      (['lift to the clinic', 'moving a fridge across town'],
                       ['have a van and a free Saturday', 'can drive locally']),
    'tutoring_math':  (['help with algebra', 'my daughter is behind in maths'],
                       ['taught secondary maths for 9 years', 'can tutor arithmetic']),
    'literacy':       (['reading practice for an adult learner'],
                       ['volunteer reading tutor']),
    'translation_es': (['need a form explained in Spanish'],
                       ['bilingual Spanish, can translate documents']),
    'translation_fr': (['a French letter I cannot read'], ['native French, will translate']),
    'legal_aid':      (['a tenancy letter I do not understand', 'landlord dispute'],
                       ['paralegal, tenancy matters', 'can read a contract with you']),
    'accounting':     (['books are a mess before filing'],
                       ['bookkeeper, small accounts']),
    'web_build':      (['a one page site for a food bank'],
                       ['front end developer, will build simple sites']),
    'data_cleanup':   (['spreadsheet of donors is a disaster'],
                       ['can clean and dedupe a dataset']),
    'grant_writing':  (['need help writing a funding application'],
                       ['have written 40 successful grants']),
    'carpentry':      (['a ramp for the front step', 'shelves for the community room'],
                       ['carpenter, weekends free']),
    'plumbing':       (['leak under the sink'], ['plumber, will do a callout']),
    'electrical':     (['sockets in the hall are dead'], ['qualified sparks']),
    'welding':        (['gate hinge has sheared'], ['can weld mild steel']),
    'sewing':         (['school uniforms need taking in'], ['machine and time to sew']),
    'cooking_bulk':   (['meals for 40 at a funeral'], ['can cook at scale']),
    'seed_saving':    (['need seed for a second planting'], ['saved seed to share']),
    'beekeeping':     (['swarm in the chimney'], ['beekeeper, will collect swarms']),
    'soil_testing':   (['is this ground safe to grow in'], ['have a soil test kit and know how']),
    'irrigation':     (['drip line for a market garden'], ['installed irrigation for years']),
    'solar_install':  (['panels bought, nobody to fit them'], ['fit domestic solar']),
    'battery_repair': (['tool batteries all dead'], ['rebuild battery packs']),
    'bicycle_repair': (['three bikes, no brakes'], ['bike mechanic']),
    'radio_comms':    (['no signal in the valley'], ['licensed radio operator']),
    'first_aid':      (['nobody here is trained'], ['first aid instructor']),
    'mental_health':  (['someone to talk to weekly'], ['trained peer supporter']),
    'childminding':   (['cover for a night shift'], ['overnight childminding']),
    'storage_space':  (['nowhere to keep donated stock'], ['dry barn, half empty']),
    'kitchen_space':  (['need a registered kitchen'], ['certified kitchen, evenings free']),
    'meeting_space':  (['room for thirty people'], ['hall available weekday evenings']),
    'transport_bulk': (['a tonne of potatoes to move'], ['lorry and a licence']),
    'cold_storage':   (['produce spoiling before it is given out'], ['walk in chiller with room']),
    'packaging':      (['need food-safe containers'], ['boxes and jars by the pallet']),
    'photography':    (['pictures for a funding bid'], ['photographer, will do it free']),
    'video_edit':     (['an hour of footage and no idea'], ['edit video, quick turnaround']),
    'bookkeeping_ngo':(['charity accounts before deadline'], ['do charity returns']),
    'fundraising':    (['no idea how to start raising'], ['ran a capital appeal']),
    'permit_help':    (['planning application refused'], ['navigate planning permits']),
    'wells_water':    (['borehole has silted up'], ['drill and maintain boreholes']),
    'goat_health':    (['herd is sick and vet is far'], ['veterinary paraprofessional']),
    'grain_milling':  (['maize to mill, no mill'], ['hammer mill, will run batches']),
    'phone_repair':   (['cracked screens, no money'], ['repair phones']),
    'literacy_digital':(['cannot use the benefits portal'], ['teach basic computer use']),
}
CONCEPT_NAMES = sorted(CONCEPTS)

URGENCY = ['whenever', 'soon', 'urgent']

# Rough UTC offsets, one per country. Rough is enough: what matters for
# matching is whether two people's working hours overlap at all.
TZ = {'US': -6, 'CA': -5, 'MX': -6, 'BR': -3, 'GB': 0, 'IE': 0, 'ES': 1,
      'FR': 1, 'DE': 1, 'KE': 3, 'NG': 1, 'ZA': 2, 'IN': 5, 'PH': 8,
      'ID': 7, 'AU': 10, 'NZ': 12, 'PL': 1, 'UA': 2, 'CO': -5}


def weighted_country(rnd):
    r, acc = rnd.random() * sum(c[1] for c in COUNTRIES), 0.0
    for c in COUNTRIES:
        acc += c[1]
        if r <= acc:
            return c
    return COUNTRIES[-1]


class Corpus:
    """Rows in memory. Nothing is written until emit()."""

    def __init__(self, seed, label, spec):
        self.rnd = random.Random(seed)
        self.run_id = str(uuid.UUID(int=random.Random(seed).getrandbits(128)))
        self.seed, self.label, self.spec = seed, label, spec
        self.members, self.needs, self.offers, self.plants = [], [], [], []
        # (country, concept) pairs withheld from every later offer, so that a
        # planted chain cannot be short-circuited by an accidental local answer
        self.reserved = set()
        # Concepts that may never be offered ANYWHERE in this corpus. Chosen
        # first, before a single offer exists, because the first version chose
        # them last -- by which point every concept already had offers and all
        # forty controls were answerable. A control group has to be built, not
        # selected after the fact.
        self.banned_concepts = set()

    def offerable(self, exclude_country=None):
        """Concepts an offer may legally use."""
        return [c for c in CONCEPT_NAMES
                if c not in self.banned_concepts
                and (exclude_country is None or (exclude_country, c) not in self.reserved)]

    # ── people ──────────────────────────────────────────────────────────────
    def make_members(self, n):
        counters = {}
        for _ in range(n):
            code, _w, lang, regions = weighted_country(self.rnd)
            counters[code] = counters.get(code, 0) + 1
            langs = [lang] if lang == 'en' else [lang, 'en']
            self.members.append({
                'id': str(uuid.UUID(int=self.rnd.getrandbits(128))),
                'handle': f'{code}-{counters[code]:03d}',
                'country': code,
                'region': self.rnd.choice(regions),
                'languages': langs,
                # UTC offset. Added because the ranking layer was measured with
                # nothing to separate one willing stranger abroad from another:
                # zero of 400 members had a timezone, and language split a
                # need's foreign candidates barely more than one way. A corpus
                # that withholds the deciding signal cannot test a decision.
                'tz': TZ[code],
            })

    def in_country(self, code):
        return [m for m in self.members if m['country'] == code]

    def member_of(self, member_id):
        return next(m for m in self.members if m['id'] == member_id)

    # ── needs and offers ────────────────────────────────────────────────────
    def add_need(self, member, concept, **kw):
        titles = CONCEPTS[concept][0]
        row = {
            'id': str(uuid.UUID(int=self.rnd.getrandbits(128))),
            'member': member['id'],
            'title': self.rnd.choice(titles),
            'concept': concept,
            'category': concept.split('_')[0],
            'language': member['languages'][0],
            'remote_ok': kw.get('remote_ok', self.rnd.random() < 0.35),
            'urgency': kw.get('urgency', self.rnd.choice(URGENCY)),
        }
        self.needs.append(row)
        return row

    def add_offer(self, member, concept, **kw):
        # blocked_on: this offer cannot be taken up until its owner's own need
        # is met. See plant_chain_only for why that is the whole point.
        # Refused rather than skipped. A silently dropped offer would leave a
        # planted chain with a missing link and the integrity view would call
        # the answer key wrong -- correctly, but a long way from the cause.
        if concept in self.banned_concepts:
            raise AssertionError(
                f'{concept} is reserved for the control group and may never be offered')
        if (member['country'], concept) in self.reserved:
            raise AssertionError(
                f'{concept} is reserved in {member["country"]} to keep a chain the only route')
        titles = CONCEPTS[concept][1]
        row = {
            'id': str(uuid.UUID(int=self.rnd.getrandbits(128))),
            'member': member['id'],
            'title': self.rnd.choice(titles),
            'concept': concept,
            'category': concept.split('_')[0],
            'language': member['languages'][0],
            'remote_ok': kw.get('remote_ok', self.rnd.random() < 0.35),
            'blocked_on': kw.get('blocked_on'),
        }
        self.offers.append(row)
        return row

    def plant(self, kind, need, chain, note):
        self.plants.append({
            'kind': kind, 'hops': len(chain), 'need': need['id'],
            'chain': [{'need_id': n['id'], 'offer_id': o['id']} for n, o in chain],
            'note': note,
        })

    # ── the classes ─────────────────────────────────────────────────────────
    def plant_direct(self, n):
        made = 0
        while made < n:
            code = weighted_country(self.rnd)[0]
            here = self.in_country(code)
            if len(here) < 2:
                continue
            asker, helper = self.rnd.sample(here, 2)
            free = self.offerable(exclude_country=code)
            if not free:
                continue
            concept = self.rnd.choice(free)
            need = self.add_need(asker, concept)
            offer = self.add_offer(helper, concept)
            self.plant('direct', need, [(need, offer)],
                       f'{asker["handle"]} needs {concept}; {helper["handle"]} offers it, same country')
            made += 1

    def plant_cross_border(self, n):
        """The only answer is abroad. Both ends must be remote_ok or the match
        is a fantasy — a matcher that proposes an in-person ramp build across
        an ocean is worse than one that proposes nothing."""
        made = 0
        while made < n:
            a, b = weighted_country(self.rnd), weighted_country(self.rnd)
            if a[0] == b[0]:
                continue
            here, there = self.in_country(a[0]), self.in_country(b[0])
            if not here or not there:
                continue
            free = [x for x in self.offerable(exclude_country=b[0])
                    if (a[0], x) not in self.reserved]
            if not free:
                continue
            concept = self.rnd.choice(free)
            # NOBODY AT HOME MAY ANSWER IT, OR IT IS NOT A CROSS-BORDER CASE.
            #   Reserving the pair stops any LATER offer landing there. It does
            #   not stop an EARLIER one, and one did: an earlier cross-border
            #   plant had already placed its helper's offer in this country,
            #   under this concept, before this plant reserved it. The claim
            #   "exists nowhere in <country>" was then false, and the matcher
            #   was marked wrong for correctly declining to route abroad when a
            #   neighbour could do it. The answer key was at fault, not the
            #   matcher. So the existing offers are checked, not just the
            #   reservations.
            if any(o['concept'] == concept and
                   self.member_of(o['member'])['country'] == a[0]
                   for o in self.offers):
                continue
            self.reserved.add((a[0], concept))
            asker, helper = self.rnd.choice(here), self.rnd.choice(there)
            need = self.add_need(asker, concept, remote_ok=True)
            offer = self.add_offer(helper, concept, remote_ok=True)
            self.plant('cross_border', need, [(need, offer)],
                       f'{concept} exists nowhere in {a[0]}; {helper["handle"]} in {b[0]} can do it remotely')
            made += 1

    def plant_chain(self, n, length, kind):
        """A chain of `length` links. Every concept used is withheld from the
        noise in the countries involved, so the chain is the ONLY route and a
        direct match cannot accidentally outrank it."""
        made = 0
        guard = 0
        while made < n and guard < n * 40:
            guard += 1
            code = weighted_country(self.rnd)[0]
            here = self.in_country(code)
            if len(here) < length + 1:
                continue
            people = self.rnd.sample(here, length + 1)
            free = self.offerable(exclude_country=code)
            if len(free) < length:
                continue
            concepts = self.rnd.sample(free, length)
            chain = []
            for i, concept in enumerate(concepts):
                need = self.add_need(people[i], concept, remote_ok=False)
                offer = self.add_offer(people[i + 1], concept, remote_ok=False)
                chain.append((need, offer))
            # RESERVED AFTER, NOT BEFORE. The reservation exists to stop any
            # LATER offer duplicating this concept in this country and handing
            # the matcher a shortcut. Setting it first made add_offer refuse
            # the chain's own link, which is the guard working and the caller
            # asking for the wrong thing.
            for concept in concepts:
                self.reserved.add((code, concept))
            names = ' -> '.join(p['handle'] for p in people)
            self.plant(kind, chain[0][0], chain,
                       f'{length} links in {code}: {names}; no single pair is a match on its own')
            made += 1

    def reserve_controls(self, n_concepts):
        """Set aside concepts nothing will ever offer. Called FIRST, before any
        offer exists, because that is the only moment at which the guarantee
        can still be made."""
        pool = list(CONCEPT_NAMES)
        self.rnd.shuffle(pool)
        self.banned_concepts = set(pool[:n_concepts])
        return sorted(self.banned_concepts)

    def plant_chain_only(self, n, length=2):
        """A need whose ONLY answer is blocked until somebody else is helped.

        THE CLASS THE FIRST CORPUS DID NOT HAVE, AND THE MEASUREMENT THAT
        EXPOSED IT.

          The original chains were sequences of ordinary matches passing
          through the same people. Every one of them started from a need that
          also had a plain direct answer -- the chain's own first link. So a
          ranker that prefers the short route put the direct candidate first,
          which is correct advice, and scored 0 of 30 against an answer key
          that called the chain right. The key was measuring the wrong thing.

          Here the helper's offer carries blocked_on: it cannot be taken up
          until that helper's own need is met. A' is not merely a nicer route,
          it is the ONLY route, and a matcher that proposes the blocked pair
          on its own is proposing something that cannot happen.

          This is the case that justifies multi-hop existing at all, and until
          now nothing was testing it.
        """
        made, guard = 0, 0
        while made < n and guard < n * 60:
            guard += 1
            code = weighted_country(self.rnd)[0]
            here = self.in_country(code)
            if len(here) < length + 1:
                continue
            people = self.rnd.sample(here, length + 1)
            free = self.offerable(exclude_country=code)
            if len(free) < length:
                continue
            concepts = self.rnd.sample(free, length)
            chain = []
            for i, concept in enumerate(concepts):
                need = self.add_need(people[i], concept, remote_ok=False)
                # Every link but the last is blocked on the NEXT need in the
                # chain: people[i+1] cannot give until people[i+1] is helped.
                blocked = (i < length - 1)
                offer = self.add_offer(people[i + 1], concept, remote_ok=False,
                                       blocked_on='PENDING')
                chain.append((need, offer))
            # Now that every need exists, point each blocked offer at the need
            # that unblocks it. Done in a second pass because the need it waits
            # on is created after the offer itself.
            for i in range(length - 1):
                chain[i][1]['blocked_on'] = chain[i + 1][0]['id']
            chain[length - 1][1]['blocked_on'] = None
            for concept in concepts:
                self.reserved.add((code, concept))
            self.plant('chain_only', chain[0][0], chain,
                       f'the only member in {code} who can answer this cannot act '
                       f'until their own need is met; the chain is the only route')
            made += 1

    def plant_unanswerable(self, n):
        """THE CONTROL GROUP.

        A need whose concept appears nowhere as an offer in the entire corpus.
        Not merely unmet -- unmeetable. add_offer refuses these concepts
        outright, so no later noise, and no later edit to this file, can quietly
        turn a control into an ordinary miss and cost the measurement its
        point."""
        assert self.banned_concepts, 'reserve_controls() must run before any offer is made'
        banned = sorted(self.banned_concepts)
        for _ in range(n):
            member = self.rnd.choice(self.members)
            concept = self.rnd.choice(banned)
            need = self.add_need(member, concept)
            self.plant('unanswerable', need, [],
                       f'nothing in this corpus offers {concept}; any suggestion here is invented')

    # ── noise ───────────────────────────────────────────────────────────────
    def add_noise(self, needs_per, offers_per):
        """Everything not planted. Reserved (country, concept) pairs are
        respected so noise cannot answer a planted question, and banned
        concepts never appear as an offer anywhere."""
        for m in self.members:
            # Needs may use any concept at all, including the banned ones --
            # unanswered needs are realistic and only the planted ones are
            # scored.
            for _ in range(self.rnd.randint(0, needs_per)):
                self.add_need(m, self.rnd.choice(CONCEPT_NAMES))
            free = self.offerable(exclude_country=m['country'])
            for _ in range(self.rnd.randint(0, offers_per)):
                if free:
                    self.add_offer(m, self.rnd.choice(free))

    # ── output ──────────────────────────────────────────────────────────────
    def statements(self):
        q = lambda s: "NULL" if s is None else "'" + str(s).replace("'", "''") + "'"
        arr = lambda xs: "ARRAY[" + ",".join(q(x) for x in xs) + "]::text[]"
        out = [
            f"INSERT INTO sim.runs (run_id, label, seed, spec) VALUES "
            f"({q(self.run_id)}, {q(self.label)}, {self.seed}, {q(json.dumps(self.spec))}::jsonb);"
        ]
        for m in self.members:
            out.append(
                "INSERT INTO sim.members (sim_member_id, run_id, handle, country, region, "
                "timezone, languages) "
                f"VALUES ({q(m['id'])}, {q(self.run_id)}, {q(m['handle'])}, {q(m['country'])}, "
                f"{q(m['region'])}, {q('UTC%+d' % m['tz'])}, {arr(m['languages'])});")
        for n in self.needs:
            out.append(
                "INSERT INTO sim.needs (sim_need_id, run_id, sim_member_id, title, category, "
                "concept, language, remote_ok, urgency) VALUES "
                f"({q(n['id'])}, {q(self.run_id)}, {q(n['member'])}, {q(n['title'])}, "
                f"{q(n['category'])}, {q(n['concept'])}, {q(n['language'])}, "
                f"{str(n['remote_ok']).lower()}, {q(n['urgency'])});")
        for o in self.offers:
            out.append(
                "INSERT INTO sim.offers (sim_offer_id, run_id, sim_member_id, title, category, "
                "concept, language, remote_ok, blocked_on) VALUES "
                f"({q(o['id'])}, {q(self.run_id)}, {q(o['member'])}, {q(o['title'])}, "
                f"{q(o['category'])}, {q(o['concept'])}, {q(o['language'])}, "
                f"{str(o['remote_ok']).lower()}, "
                f"{'NULL' if not o.get('blocked_on') else q(o['blocked_on']) + '::uuid'});")
        for p in self.plants:
            out.append(
                "INSERT INTO sim.planted (run_id, kind, hops, sim_need_id, chain, note) VALUES "
                f"({q(self.run_id)}, {q(p['kind'])}, {p['hops']}, {q(p['need'])}, "
                f"{q(json.dumps(p['chain']))}::jsonb, {q(p['note'])});")
        return out


def build(seed, members, label):
    # The mix. Direct matches dominate because they do in life; the chains are
    # a minority precisely because they are the interesting minority.
    spec = {
        'members': members,
        'direct': max(2, members // 8),
        'cross_border': max(1, members // 16),
        'hop2': max(1, members // 20),
        'hop3': max(1, members // 40),
        'chain_only': max(1, members // 20),
        'unanswerable': max(2, members // 10),
        'noise_needs_per_member': 2,
        'noise_offers_per_member': 2,
    }
    c = Corpus(seed, label, spec)
    c.make_members(members)
    # BEFORE ANYTHING ELSE. Once an offer exists the control group can no
    # longer be guaranteed, only hoped for.
    spec['control_concepts'] = c.reserve_controls(max(3, len(CONCEPT_NAMES) // 7))
    # ORDER MATTERS. Chains and cross-border plants reserve concepts; the
    # control group picks from what is left; noise is generated last so it can
    # respect every reservation made above it. Generating noise first would
    # quietly answer half the planted questions.
    c.plant_chain_only(spec['chain_only'], 2)
    c.plant_chain(spec['hop3'], 3, 'hop3')
    c.plant_chain(spec['hop2'], 2, 'hop2')
    c.plant_cross_border(spec['cross_border'])
    c.plant_direct(spec['direct'])
    c.plant_unanswerable(spec['unanswerable'])
    c.add_noise(spec['noise_needs_per_member'], spec['noise_offers_per_member'])
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=20260919)
    ap.add_argument('--members', type=int, default=400)
    ap.add_argument('--label', default=None)
    ap.add_argument('--dsn', help='write straight into a database')
    ap.add_argument('--print-sql', action='store_true')
    a = ap.parse_args()

    label = a.label or f'corpus-{a.members}-seed-{a.seed}'
    c = build(a.seed, a.members, label)
    stmts = c.statements()

    if a.print_sql:
        print('\n'.join(stmts))
    elif a.dsn:
        import psycopg
        with psycopg.connect(a.dsn) as conn:
            with conn.cursor() as cur:
                for s in stmts:
                    cur.execute(s)
            conn.commit()
    else:
        print(__doc__.splitlines()[0])
        print('\nNothing written — pass --dsn or --print-sql.\n')

    kinds = {}
    for p in c.plants:
        kinds[p['kind']] = kinds.get(p['kind'], 0) + 1
    print(f"\n  run_id   {c.run_id}", file=sys.stderr)
    print(f"  seed     {a.seed}", file=sys.stderr)
    print(f"  members  {len(c.members)} across "
          f"{len({m['country'] for m in c.members})} countries", file=sys.stderr)
    print(f"  needs    {len(c.needs)}    offers {len(c.offers)}", file=sys.stderr)
    for k in sorted(kinds):
        print(f"  {k:<14}{kinds[k]}", file=sys.stderr)
    print("\n  Read sim.v_plant_integrity before believing any score.\n", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
