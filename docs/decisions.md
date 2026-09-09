# Decisions

Recorded so none of them gets taken twice.

## Lending eligibility inputs

Six inputs, all synthetic: `loans_repaid`, `missed_payments_last_12m`, `outstanding_balance`,
`average_monthly_revenue`, `requested_amount`, `sector`. Version 2 adds `bureau_score` and
`bureau_status`, both optional, filled by the bureau integration. Declared in
`rulesets/lending/ruleset.py` with types, and validated before a run starts.

## Exceptions resolve one at a time

Bulk resolution would mean one note covering many different reasons, which is a worse audit
trail, and it is the larger build.

## Ruleset versions are files, not rows

A version is a Python class, registered under a name and a version string, and the decision
record stores both strings. Diffable, reviewed in a pull request, and a threshold change is a new
class rather than an edit. Rows would allow a change without a deploy, but that is what rollout
flags are for: the flag is the row, the version is the file.

## Pinned versions

| Component | Version | Pinned in |
|---|---|---|
| Python | 3.12 | `.python-version`, read by CI and the Dockerfile base image |
| Node | 24 | `.nvmrc`, read by CI and the frontend Dockerfile |
| Django | 5.2.17 | `requirements.txt` |
| PostgreSQL | 17 | `docker-compose.yml` and the CI service |

Postgres is named in two places. Both say 17.

## App Runner, not Fargate

One container, no load balancer to configure, and a VPC connector to reach RDS. The Terraform in
`infra/` is written and validated but not applied, so there is no live URL and the README does
not claim one.

## Where the abstraction leaked

Two places, both found by running the metering ruleset through the engine built for lending.

1. The engine's amount stage declined any run whose amount was zero. Right for a loan, wrong for
   a meter with no consumption, where a zero charge is a decision. The check moved out of the
   engine into a lending rule, `MinimumOffer`.
2. Rollout flags bucket on the subject of the decision. In lending the subject is the customer,
   which is the unit anyone wants to roll out by. In metering the subject is a meter, and a
   customer can have several, so a percentage rollout can put one customer's meters on two
   versions. Not fixed. The fix is a separate rollout key on the subject, which lending does not
   need.

A third finding was a bug rather than a leak: a human confirming a meter rollover left the
engine computing consumption from the raw reads, which came out negative. The rollover rule now
decides the consumption, so an override has to state it.
