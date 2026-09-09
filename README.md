# repeat-offer-pipeline

[![CI](https://github.com/dollarmatian/repeat-offer-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/dollarmatian/repeat-offer-pipeline/actions/workflows/ci.yml)

A staged decision engine: eligibility, then price, then amount. Every run writes a decision
record you can query afterwards, anything it will not decide goes to a human, and a change ships
behind a flag so two versions can be compared.

## Why

Six months later somebody asks why a particular customer got the offer they got, and by then the
code has moved on. Rules written as a call chain can answer "what does this do now". They cannot
answer "what did this do in March".

So a rule is a class with a declared shape: the stage it runs in, the inputs it reads, the values
it decides. A rule reading an input it did not declare is an error, not a decision. A decision
is a record rather than a log line: the inputs, the ruleset version, the flag state, every rule
that ran and why, and the outcome. The same inputs under the same version return the record
already written rather than writing a second one.

## Rulesets

The engine knows nothing about lending. Two rulesets run through it, which is how that claim gets
tested rather than asserted.

* `rulesets/lending/` models the shape of a repeat offer pipeline on synthetic data. Not a credit
  model and makes no claim to be one.
* `rulesets/metering/` turns meter reads into a charge. The domain I worked in for three and a
  half years.

Running metering through an engine built for lending found two leaks. The engine declined any run
whose amount was zero, which is right for a loan and wrong for a meter with no consumption, so
that check is now a lending rule. Rollout flags bucket on the subject of the decision, which in
lending is the customer and in metering is the meter, so a percentage rollout can split one
customer's meters across two versions. That one is still there. `docs/decisions.md` has both.

## Running it

```
docker compose up --build
docker compose run --rm app ./manage.py run_pipeline lending examples/lending.json
```

API on `http://localhost:8000/api/`, exception queue on `http://localhost:5173`. The command
runs the file in one transaction and is safe to re-run.

One decision over HTTP:

```
curl -X POST localhost:8000/api/decisions/ -H 'Content-Type: application/json' -d '{
  "ruleset": "metering", "subject_reference": "MPAN-1",
  "inputs": {"previous_read": 1000, "current_read": 1300, "days_in_period": 30,
             "read_source": "smart", "tariff_code": "standard"}}'
```

`GET /api/exceptions/` lists what needs a human, `POST /api/exceptions/<id>/resolve/` writes the
answer to the same record, and `GET /api/metrics/` counts by outcome, stage and ruleset version.
`./manage.py set_flag` routes a subset of subjects to a version without a deploy, and
`./manage.py list_rules` prints every rule in run order.

Without Docker: Python 3.12, Node 24 and a Postgres at `DATABASE_URL`, then
`pip install -r requirements-dev.txt`, `./manage.py migrate`, `./manage.py runserver`, and
`npm install && npm run dev` in `frontend/`.

## Tests

```
docker compose run --rm app pytest      # rules, sequencing, records, migration, integration
docker compose run --rm web npm test    # exception queue
```

Both run against a real Postgres, both run on every push, and the badge above is the last run.

## Trade-offs

* **Rulesets are files, not rows.** A version is a class, reviewed and diffable. It costs a
  deploy to add one. Flags are the rows, and they decide who gets which version
* **A human override re-runs the rules.** Resolving an exception overrides the one rule that
  referred and lets the rest run, so a human answers only the question asked. It costs a second
  pass on the record, kept as attempt two, and a human can be referred twice
* **The public reference changed after ids had been issued.** Migration 0002 backfills, and both
  forms resolve. `docs/preserving-references.md` has the reasoning
* **pytest, not `django.test.TestCase`.** pytest in a new repo. In a codebase already using
  Django's own suite, use theirs

## Limitations

* Both rulesets are synthetic and validated against nothing real
* Records are append-only but not sealed. Real audit would want tamper evidence
* Nobody is authenticated. The queue takes a name and believes it
* The Terraform in `infra/` is validated, not applied. There is no live URL
* Migrations run at container start, which is wrong for more than one instance

## What I'd change at 100x

Decisions become a stream so a slow rule cannot hold a request open. The record moves to
append-only storage with the queryable copy as a projection, and metrics read a daily rollup
rather than the join in `docs/query-plan.md`. Rules get a time budget and per-rule timing. The
queue gets priority, and the bureau client gets a circuit breaker so a dead upstream stops
costing a timeout per subject.

## Licence

MIT.
