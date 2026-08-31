# repeat-offer-pipeline

A staged decision engine for repeat lending offers: eligibility, then price, then amount.
Every run writes a decision record you can query afterwards.

Work in progress. Started 1 September 2026, shipping 14 September 2026.

## What does this do?

* Runs a case through three stages in order, each one an explicit rule that can be tested on its own
* Writes a decision record for every run: the inputs, which rules fired, which did not, and the output
* Sends anything it will not decide to a queue for a human
* Ships a change behind a flag with the old path still runnable, so the two can be compared

## Why not just write the rules inline?

Six months later somebody asks why a particular customer got the offer they got, and by then the
code has moved on. Rules written as a call chain can answer "what does this do now". They cannot
answer "what did this do in March".

So rules are declared classes rather than functions in a chain, and a decision is a record rather
than a log line. Thresholds live in a ruleset, so changing what the business offers is a config
change and not a deploy.

## Rulesets

The engine knows nothing about lending. Two rulesets ship with it, which is how that claim gets
tested rather than asserted.

* `rulesets/lending/` : eligibility, price and amount for a repeat offer. The rules are synthetic.
  This is a decisioning and audit pipeline, not a credit model, and makes no claim to be one.
* `rulesets/metering/` : meter reads to a charge. Which reads are valid, which tariff applies, what
  the customer is billed. Three and a half years of my working life, and the reason the design looks
  like this.

## How do I run it?

```
docker compose up --build
docker compose run --rm app ./manage.py migrate
docker compose run --rm app ./manage.py load_ruleset lending
```

App on `http://localhost:8000`, exception queue on `http://localhost:5173`.

Without docker: Python 3.12, Node 20 and a local PostgreSQL, then `pip install -r
requirements-dev.txt`, `./manage.py migrate`, `./manage.py runserver`.

## How do I run the tests?

```
docker compose run --rm app pytest        # engine, rules, one end-to-end path
docker compose run --rm web npm run test  # Vitest, exception queue
```

Both run on every push in GitHub Actions.

## What does this not do?

* Validate its rules against anything real. Both rulesets are synthetic
* Seal the decision records. They are append-only, but real audit would want tamper evidence
* Authenticate anybody. The exception queue has no user model
* Version rulesets properly. Versioning is by directory, and changing a rule's shape leaves you to
  decide what happens to the records already written

## Trade-offs

* **A separate FastAPI service for decisioning.** Buys independent versioning and replay of
  decisions. Costs a network hop and a second thing to deploy. Wrong trade on latency alone, right
  one here, because re-running last month's decisions against last month's rules is the requirement
* **A flag rather than a cutover.** Two live code paths is a real maintenance cost and an invitation
  to leave both there forever, so the flag carries the date it gets deleted
* **pytest, not `django.test.TestCase`.** pytest in a new repo. In a codebase already using Django's
  own test suite, use theirs. Restructuring someone else's test framework is not initiative

## What's still to come?

* The metering ruleset, and the two places the abstraction leaks
* Deployment, a live URL, and the Terraform for it
* `docs/ai-log.md`: what got delegated, what was done by hand, and what had to be corrected

At 100x the volume: decisions become a stream so a slow rule cannot hold a page open, the record
moves to append-only storage with the queryable copy as a projection, rule evaluation gets a cost
budget and per-rule timing, and the exception queue gets prioritisation.

## Licence

MIT.
