import type { DecisionRecord } from "../api";

function show(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function DecisionRecordView({ record }: { record: DecisionRecord }) {
  return (
    <section aria-label="Decision record">
      <h2>
        Decision <code>{record.reference}</code>
      </h2>
      <dl className="grid">
        <dt>Subject</dt>
        <dd>{record.subject_reference}</dd>
        <dt>Ruleset</dt>
        <dd>
          {record.ruleset} v{record.version}
        </dd>
        <dt>Outcome</dt>
        <dd>
          <span className={`outcome ${record.outcome}`}>{record.outcome}</span>
          {record.stopped_at_stage ? ` at ${record.stopped_at_stage}` : ""}
        </dd>
        <dt>Flag state</dt>
        <dd>
          <code>{show(record.flag_state)}</code>
        </dd>
        <dt>Decided</dt>
        <dd>
          <code>{show(record.decision)}</code>
        </dd>
        <dt>Created</dt>
        <dd>{new Date(record.created_at).toLocaleString()}</dd>
      </dl>

      <h3>Inputs</h3>
      <table>
        <tbody>
          {Object.entries(record.inputs).map(([key, value]) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              <td>{show(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Rules, in the order they ran</h3>
      <table>
        <thead>
          <tr>
            <th>Attempt</th>
            <th>Stage</th>
            <th>Rule</th>
            <th>Outcome</th>
            <th>Reason</th>
            <th>Decided</th>
          </tr>
        </thead>
        <tbody>
          {record.stages.map((s) => (
            <tr key={`${s.attempt}-${s.position}`} className={s.overridden ? "overridden" : ""}>
              <td>{s.attempt}</td>
              <td>{s.stage}</td>
              <td>
                <code>{s.rule}</code>
                {s.overridden ? " (overridden)" : ""}
              </td>
              <td>
                <span className={`outcome ${s.outcome}`}>{s.outcome}</span>
              </td>
              <td>{s.reason}</td>
              <td>{Object.keys(s.values).length ? <code>{show(s.values)}</code> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
