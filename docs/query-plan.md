# One query plan, read

The metrics endpoint's "by stage" count is the heaviest query in the project: it joins every
stage outcome to its record, filters by ruleset, and groups. Read on a dev database seeded with
5,962 records and 25,126 stage outcomes, Postgres 17.

```sql
SELECT s.stage, s.outcome, COUNT(*)
FROM engine_stageoutcome s
JOIN engine_decisionrecord r ON r.id = s.record_id
WHERE r.ruleset_name = 'lending' AND s.attempt = 1
GROUP BY s.stage, s.outcome
```

```
HashAggregate  (actual time=4.897..4.898 rows=6 loops=1)
  Group Key: s.stage, s.outcome
  ->  Hash Join  (actual time=0.583..3.515 rows=16985 loops=1)
        Hash Cond: (s.record_id = r.id)
        ->  Seq Scan on engine_stageoutcome s  (actual rows=25126)
              Filter: (attempt = 1)
              Buffers: shared hit=397
        ->  Hash  (rows=4000)
              ->  Seq Scan on engine_decisionrecord r  (actual rows=4000)
                    Filter: ((ruleset_name)::text = 'lending'::text)
                    Rows Removed by Filter: 1962
                    Buffers: shared hit=351
Execution Time: 4.936 ms
```

## What it says

Two sequential scans and a hash join, five milliseconds, everything from shared buffers. The
planner is right to ignore every index on these tables: `attempt = 1` matches two thirds of the
outcomes, `ruleset_name = 'lending'` matches two thirds of the records, and both tables fit in
under 400 pages each. An index that returns most of a table costs more than reading the table.

Adding `(record_id, attempt)` on the outcomes table changes nothing: same plan, same time.
To check, run `CREATE INDEX tmp ON engine_stageoutcome (record_id, attempt)`, `ANALYZE`, and
the `EXPLAIN` again. The `record_ruleset_outcome` index the model declares is unused here for
the same reason. It exists for the `by_ruleset` split, and it earns its keep only once one
ruleset is a small fraction of the table.

## What changes at scale

Stage outcomes grow at roughly four to eight rows per decision. At ten million decisions this is
a sixty million row join done on every metrics call. Two things fix it, in order:

1. Filter by time. The endpoint already accepts `since`, and `record_created` is indexed, so a
   dashboard asking about the last day touches a slice rather than the table.
2. Roll it up. Counts by stage, outcome and ruleset version per day is a small table that a
   nightly job or a trigger maintains, and the endpoint reads that. The record stays the source
   of truth; the rollup is a projection.

Neither is built. At the volume a demo sees, the honest plan is the one above.
