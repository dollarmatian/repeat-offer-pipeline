# repeat-offer-pipeline

A staged decision engine (**eligibility → price → amount**) with a decision record for
every run, feature-flagged rollout, and a human exception queue.

**Status: in progress. Started 1 September 2026, shipping 14 September 2026.**
This README was written before the code, deliberately. The design is the part worth
reviewing, and it should be reviewable from day one.

## What problem this solves

A lender making a repeat offer to an existing customer answers three questions in order:
is this customer eligible, what price do they get, and how much can they borrow. Months
later, it has to answer a fourth: **why did this customer get this offer?**

Most implementations answer the first three and lose the fourth. The rules end up spread
through the code path that runs them, so a past decision cannot be reconstructed once the
code has moved on, and changing a threshold means a redeploy.

This is that pipeline built the other way round. Each stage is an explicit, individually
testable rule, and every run writes a decision record that can be queried afterwards: the
inputs, which rules fired, which did not, and the output.

## Why this shape and not the obvious one

- **Rules are declared classes, not functions in a call chain.** A rule with a declared
  shape can be tested on its own and named in a decision record. A function buried in a
  pipeline can be neither.
- **A decision record per run, not a log line.** Logs are for debugging. The record is the
  product: "why did this customer get this offer" should be a query, not archaeology.
- **Rules are configuration.** Thresholds, bands and caps live in a ruleset, not in the
  engine. Changing what the business offers should not mean changing how offers are made.
- **The new path ships behind a feature flag with the old path still runnable**, so the two
  can be compared on the same inputs. A cutover tells you nothing about whether the change
  was an improvement.
- **The decisioning stage is a separate FastAPI service that Django calls.** The decision is
  the part that has to be replayable and versioned independently of the web app that
  triggers it. This costs a network hop; see Trade-offs.

## Rulesets

The engine is domain-agnostic. It ships with two rulesets, which is how that claim gets
tested rather than asserted.

- **`rulesets/lending/`**: the shape of a repeat offer pipeline, being eligibility, price
  and amount. *The rules here are illustrative and synthetic. This is a decisioning and audit
  pipeline, not a credit model, and makes no claim to be one.*
- **`rulesets/metering/`**: utility meter reads to a charge, so which reads are valid, which
  tariff applies, and what the customer is billed. This is the domain I worked in for three
  and a half years, and it is the reason for the design decisions above: the same
  three-stage shape, and the same requirement to explain a number to a customer months after
  it was produced.

The second ruleset is not decoration. Running a genuinely different domain through the same
engine is what shows the abstraction is real, and it is where the two places it leaks are
documented under Limitations.

## Architecture

    ingest  →  eligibility  →  price  →  amount  →  decision record
                    ↓             ↓         ↓
                       exception queue (human review)
                                  ↓
                            metrics endpoint

| Component | What it is |
|---|---|
| `engine/` | Stages, rule base class, decision records, flag evaluation |
| `rulesets/` | The two rulesets. No engine code |
| `decisions/` | Django app: models, migrations, the queryable decision record |
| `decisioning/` | FastAPI service. Takes a case and a ruleset version, returns a decision |
| `web/` | React + TypeScript exception queue, the human-in-the-loop screen |
| `infra/` | Terraform for the AWS pieces: service, database, networking |

PostgreSQL throughout, with indexes on the decision query paths and reversible migrations.

## Running it

Docker first:

    docker compose up --build
    docker compose run --rm app ./manage.py migrate
    docker compose run --rm app ./manage.py load_ruleset lending

The app is then on `http://localhost:8000`, the exception queue on `http://localhost:5173`.

Manual setup, if you would rather not use Docker: Python 3.12, Node 20, a local PostgreSQL,
then `pip install -r requirements-dev.txt`, `./manage.py migrate`, `./manage.py runserver`.

## Tests

    docker compose run --rm app pytest          # engine, rules, and one end-to-end path
    docker compose run --rm web npm run test    # Vitest, exception queue

Both suites run on every push in GitHub Actions.

## Trade-offs

**Splitting decisioning into a FastAPI service.** It buys independent versioning and
replay of decisions, and a clean boundary to test against. It costs a network hop on every
decision and a second thing to deploy. At this volume that is the wrong trade on latency
alone; it is the right one on being able to re-run last month's decisions against last
month's rules, which is the requirement that actually matters here.

**Feature flag rather than cutover.** Two code paths live at once is a real maintenance
cost and an invitation to leave both there forever. The mitigation is a date on the flag,
recorded in the ruleset, after which the old path is deleted.

**Synthetic rules.** The lending thresholds are invented. This deliberately makes no claim
about credit quality. The subject is the machine that runs rules and explains its output,
which is an engineering problem, not a credit-risk one.

**pytest here, `django.test.TestCase` elsewhere.** pytest with `pytest-django` is the
choice in a new repo. In a codebase that already uses Django's own test suite, the right
answer is to use theirs. Restructuring someone else's test framework is not initiative.

## Limitations

Stated plainly, because they are the interesting part:

- The rulesets are synthetic and not validated against real lending or real tariffs.
- Decision records are append-only but not cryptographically sealed. Real audit would want
  tamper evidence.
- The exception queue has no authentication or role model.
- Ruleset versioning is by directory, not by a migration path. Changing a rule's shape
  requires a decision about historical records that this does not yet make for you.
- (To be filled once the metering ruleset is in: the two places the abstraction leaked.)

## What I would change at 100× the volume

- Decisions become a stream, not a synchronous call. The web request records intent; the
  engine consumes it, so a slow rule cannot hold a customer's page open.
- The decision record moves to append-only storage with a retention policy, and the
  queryable copy becomes a projection of it.
- Rule evaluation gets a cost budget and per-rule timing, so a rule that becomes expensive
  is visible before it becomes an incident.
- The exception queue gets prioritisation, because at that volume a FIFO queue is the same
  as no queue.

## Licence

MIT.
