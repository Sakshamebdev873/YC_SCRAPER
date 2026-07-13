"""Sales-pitch domain — cold emails pitching Corpus Carbon & Chemicals
(corpuscarbon.com), an India-based manufacturer/exporter of activated carbon
and anthracite filter media, on behalf of Karan.

Two ICPs, selected with --icp:
  - "traders" (default)  — activated carbon traders/distributors. Pitch:
    direct manufacturer pricing, batch-certified quality, bulk export.
  - "professionals"      — law/accounting firm owners or marketing
    directors (10+ employees). Pitch: activated carbon filter media for
    office HVAC/odor control.

There's no real sales-lead list yet, so load_rows() generates a handful of
random placeholder companies per ICP so the rest of the pipeline
(personalization, dedup, follow-ups, sent-log tracking) can be exercised
end-to-end. Once a real lead source exists, swap load_rows() for a CSV/API
loader — everything else already works against any domain that returns rows
in this shape.
"""

import random

# No real leads yet — every send in this domain is routed here instead of a
# live inbox, unless the caller passes an explicit --test-email.
DEFAULT_TEST_EMAIL = "vinodarya344@gmail.com"

SIGN_OFF = "Karan\nCorpus Carbon & Chemicals\nhttps://corpuscarbon.com"

CORPUS_CARBON_PITCH_TRADERS = """
- Corpus Carbon & Chemicals — India-based MSME manufacturer & exporter of activated carbon and anthracite filter media
- 8 carbon grades: coconut shell & coal-based activated carbon, GAC, PAC, pellet carbon, gold recovery carbon (CIP/CIL/CIC), anthracite filter media, calcined anthracite
- Direct manufacturer pricing — no middleman markup — with full COA/TDS/MSDS on every batch
- Bulk export capacity, worldwide shipping, all mesh sizes and iodine values (800-1200 mg/g) available to spec
- Site: https://corpuscarbon.com
""".strip()

CORPUS_CARBON_PITCH_PROFESSIONALS = """
- Corpus Carbon & Chemicals — India-based manufacturer of activated carbon filter media, including pellet-form carbon used in air/VOC/odor filtration
- Can supply activated carbon filter media in the mesh sizes and quantities needed for office HVAC/odor-control filter replacements
- Direct manufacturer pricing, batch-certified (COA/TDS/MSDS) — relevant for firms that manage their own building's air system or work with a facilities vendor
- Site: https://corpuscarbon.com
""".strip()

# ── Initial email prompts — target ~90 words ──────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE_TRADERS = """You write short cold outreach emails from Karan, of Corpus Carbon & Chemicals, pitching activated carbon supply to activated carbon traders/distributors. These must NOT read like a mass sales blast — no bullet lists, no "here's what we offer" section, no buzzword-stuffed pitch deck. Write like a supplier who looked at this specific trading company's business and has a concrete, specific reason to reach out about becoming a supply source.

Write the email as flowing prose (no headers, no bullets), following this shape:

1. Opening (2-3 sentences): reference something specific and real about [company]'s trading/distribution business, then connect it naturally to Corpus Carbon as a direct manufacturer source — e.g. cutting out a middleman markup, or consistent batch-certified supply for whatever grade they move. Keep it a genuine, specific observation, not a generic compliment.
2. One or two sentences on Corpus Carbon itself — pick only what's relevant (which carbon grade fits their likely trade, direct manufacturer pricing, full COA/TDS/MSDS certification, bulk export capacity) — never dump all of it.
3. On its own line: "Corpus Carbon: https://corpuscarbon.com"
4. A low-key, specific closing ask. Vary the phrasing across emails. Something like "Worth comparing a quote against your current supplier?" or "Want a sample batch sent over?" or "Open to a quick call on your current sourcing?".
5. Sign-off, exactly:
{sign_off}

Corpus Carbon background (pick 1-2 relevant details — never dump all of it):
{pitch}

Hard rules:
- 70-100 words total.
- Never use these phrases: "I hope this email finds you", "I came across your company", "I'm excited/passionate about", "reaching out", "synergy", "circle back", "game-changer".
- No bullet points, no markdown formatting, no headers.
- Should read like one supplier emailing a trading company about a specific sourcing fit, not a sales deck.
- Return only the email body — no subject line, no commentary."""

_SYSTEM_PROMPT_TEMPLATE_PROFESSIONALS = """You write short cold outreach emails from Karan, of Corpus Carbon & Chemicals, pitching activated carbon filter media for office air/odor control to owners or marketing directors at law and accounting firms. These must NOT read like a mass sales blast — no bullet lists, no "here's what we offer" section, no buzzword-stuffed pitch deck. Write like someone who thought about what a professional-services office of this size actually deals with (client-facing space, odor/air quality complaints) and has a concrete, low-key reason to mention this.

Write the email as flowing prose (no headers, no bullets), following this shape:

1. Opening (2-3 sentences): reference something specific and real about running a client-facing office like [company]'s — e.g. air quality/odor in shared spaces reflecting on the firm — then connect it naturally to activated carbon filter media as a straightforward fix for HVAC/odor control. Keep it a genuine, specific observation, not a generic compliment.
2. One or two sentences on Corpus Carbon itself — pick only what's relevant (direct manufacturer pricing, batch-certified filter media, mesh sizes/quantities to spec) — never dump all of it.
3. On its own line: "Corpus Carbon: https://corpuscarbon.com"
4. A low-key, specific closing ask. Vary the phrasing across emails. Something like "Worth a quick chat with whoever handles your office facilities?" or "Want me to send over spec sheets for your building's system?" or "Any interest in a sample for your building's HVAC filters?".
5. Sign-off, exactly:
{sign_off}

Corpus Carbon background (pick 1-2 relevant details — never dump all of it):
{pitch}

Hard rules:
- 70-100 words total.
- Never use these phrases: "I hope this email finds you", "I came across your company", "I'm excited/passionate about", "reaching out", "synergy", "circle back", "game-changer".
- No bullet points, no markdown formatting, no headers.
- Should read like a low-key, specific note, not a sales deck.
- Return only the email body — no subject line, no commentary."""

_USER_PROMPT_TEMPLATE = """Write the email for {company_name}, which is {company_description}.

Contact's first name: {founder_first_name}

Open with "Hi {founder_first_name}," then write the rest of the email per the system instructions."""

_SUBJECT_TEMPLATE_TRADERS = "Direct-from-manufacturer activated carbon for {company_name}"
_SUBJECT_TEMPLATE_PROFESSIONALS = "Activated carbon filter media for the office at {company_name}"

_FOLLOWUP_SUBJECT_TEMPLATE_TRADERS = "Re: activated carbon supply for {company_name}"
_FOLLOWUP_SUBJECT_TEMPLATE_PROFESSIONALS = "Re: office air filter media for {company_name}"

_FOLLOWUP_BODIES_TRADERS = [
    None,
    """\
Just following up on my note below about supplying activated carbon to {company_name} direct from the manufacturer.

Happy to send over a quote or a sample batch if useful.

Corpus Carbon: https://corpuscarbon.com

{sign_off}""",
    """\
One more follow-up on activated carbon supply for {company_name}. Happy to just send a quote alongside your current supplier's so you can compare.

Corpus Carbon: https://corpuscarbon.com

{sign_off}""",
    """\
Last follow-up — completely understand if the timing isn't right. If {company_name} ever wants a second source for activated carbon, I'd love to reconnect.

Corpus Carbon: https://corpuscarbon.com

{sign_off}""",
]

_FOLLOWUP_BODIES_PROFESSIONALS = [
    None,
    """\
Just following up on my note below about activated carbon filter media for {company_name}'s office HVAC.

Happy to send spec sheets or a sample if useful.

Corpus Carbon: https://corpuscarbon.com

{sign_off}""",
    """\
One more follow-up on filter media for {company_name}. Happy to loop in whoever handles your building's facilities directly.

Corpus Carbon: https://corpuscarbon.com

{sign_off}""",
    """\
Last follow-up — completely understand if it's not a priority right now. If office air/odor filtering ever comes up for {company_name}, I'd love to reconnect.

Corpus Carbon: https://corpuscarbon.com

{sign_off}""",
]

# ── Placeholder lead generation (no real sales list yet) ──────────────────────

_TRADER_PREFIXES = ["Global", "Continental", "Apex", "Meridian", "Pacific", "Atlas", "Summit", "Vantage"]
_TRADER_SUFFIXES = [" Carbon Traders", " Activated Carbon Co.", " Carbon Trading Co.", " Filtration Supplies"]
_TRADER_TOPICS = [
    "an importer of bulk activated carbon for water treatment plants",
    "a distributor of granular activated carbon to industrial buyers",
    "a supplier of activated carbon to pharma and food-grade filtration customers",
    "a reseller of coal-based activated carbon to mining operations",
    "a trading company sourcing carbon for gold recovery circuits",
]
_TRADER_TITLES = ["Owner", "Director", "Procurement Head"]

_FIRM_SURNAMES = ["Whitfield", "Hargrove", "Delacroix", "Bramwell", "Osei", "Kapoor", "Lindqvist", "Marchetti"]
_FIRM_SUFFIXES = [" & Associates", " Law Group", " LLP", " Partners", " Accounting Group"]
_FIRM_TOPICS = ["a law firm", "an accounting firm"]
_FIRM_TITLES = ["Owner", "Marketing Director"]

_FIRST_NAMES = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Jamie"]

_ICP_DEFAULT_COUNTS = {"traders": 2, "professionals": 5}


def _random_trader_name(rng: random.Random) -> str:
    return f"{rng.choice(_TRADER_PREFIXES)}{rng.choice(_TRADER_SUFFIXES)}"


def _random_firm_name(rng: random.Random) -> str:
    return f"{rng.choice(_FIRM_SURNAMES)}{rng.choice(_FIRM_SUFFIXES)}"


def load_rows(args) -> list[dict]:
    """Generates a batch of random placeholder companies for the selected ICP.

    Stand-in for a real sales-lead source. Each row gets a distinct synthetic
    predicted_email so sent_log dedup/follow-up tracking works per-lead even
    though every actual send is redirected to DEFAULT_TEST_EMAIL.
    """
    icp = getattr(args, "icp", None) or "traders"
    count = args.max if args.max > 0 else _ICP_DEFAULT_COUNTS[icp]
    rng = random.Random()
    rows = []
    seen_names = set()

    if icp == "traders":
        name_fn, topics, titles = _random_trader_name, _TRADER_TOPICS, _TRADER_TITLES
    else:
        name_fn, topics, titles = _random_firm_name, _FIRM_TOPICS, _FIRM_TITLES

    while len(rows) < count:
        name = name_fn(rng)
        if name in seen_names:
            continue
        seen_names.add(name)
        description = rng.choice(topics)
        if icp == "professionals":
            description += " with 10+ employees"
        rows.append({
            "company_name": name,
            "batch": "N/A",
            "company_website": "",
            "company_description": description,
            "founder_name": rng.choice(_FIRST_NAMES),
            "founder_title": rng.choice(titles),
            "predicted_email": f"{icp}-lead-{len(rows) + 1}@example.local",
        })
    return rows


def _resolve(icp: str):
    if icp == "traders":
        return (
            _SYSTEM_PROMPT_TEMPLATE_TRADERS.format(sign_off=SIGN_OFF, pitch=CORPUS_CARBON_PITCH_TRADERS),
            _SUBJECT_TEMPLATE_TRADERS,
            _FOLLOWUP_SUBJECT_TEMPLATE_TRADERS,
            [None if b is None else b.format(company_name="{company_name}", sign_off=SIGN_OFF) for b in _FOLLOWUP_BODIES_TRADERS],
        )
    return (
        _SYSTEM_PROMPT_TEMPLATE_PROFESSIONALS.format(sign_off=SIGN_OFF, pitch=CORPUS_CARBON_PITCH_PROFESSIONALS),
        _SUBJECT_TEMPLATE_PROFESSIONALS,
        _FOLLOWUP_SUBJECT_TEMPLATE_PROFESSIONALS,
        [None if b is None else b.format(company_name="{company_name}", sign_off=SIGN_OFF) for b in _FOLLOWUP_BODIES_PROFESSIONALS],
    )


USER_PROMPT_TEMPLATE = _USER_PROMPT_TEMPLATE


def get_prompts(args):
    """Returns (system_prompt, subject_template, followup_subject_template, followup_bodies) for args.icp."""
    icp = getattr(args, "icp", None) or "traders"
    return _resolve(icp)
