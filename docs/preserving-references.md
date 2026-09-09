# The migration that had to preserve something

Migration `0002_decisionrecord_reference` changes what a decision is called in public without
breaking anything that already held the old name.

## What changed

Until 0002 a decision's public reference was its integer primary key: `/api/decisions/17/`, and
the exception queue linked to the same number. Two problems with that. The number leaks how many
decisions exist, and it cannot be known until the row is inserted, which rules out handing a
reference to a caller before the write commits.

New records now get `dec_` followed by sixteen hex characters, generated before the insert.

## What had to survive

Any reference already issued. Links in the queue, numbers in support tickets, ids someone pasted
into a spreadsheet. A migration that renumbered them would break every one.

## How

Three operations in one migration:

1. Add `reference` as nullable, so existing rows are untouched.
2. Backfill every existing row with `dec_legacy_<id>`, a value derived from the id it already
   had, so it is stable and reversible.
3. Alter the column to non-null and unique.

Then the lookup accepts both forms. `DecisionRecord.objects.by_reference("17")` resolves by
id and `by_reference("dec_legacy_17")` resolves by reference, and they return the same row. The
URL pattern takes a string, so `/api/decisions/17/` still returns what it always did.

## Tested how

`tests/test_migration_reference.py` migrates the test database back to 0001, inserts a record
the old way, migrates forward, and asserts that the old numeric reference and the backfilled one
both resolve to it. The API test checks the same through the URL.

## What it cost

Two lookup paths where one would do, and a `dec_legacy_` prefix that will be in the data for as
long as those rows are. Both are cheaper than a broken link.
