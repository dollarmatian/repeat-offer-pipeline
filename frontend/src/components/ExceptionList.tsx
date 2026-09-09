import type { ExceptionSummary } from "../api";

interface Props {
  exceptions: ExceptionSummary[];
  status: "open" | "resolved";
  onStatusChange(status: "open" | "resolved"): void;
  onOpen(id: number): void;
}

export function ExceptionList({ exceptions, status, onStatusChange, onOpen }: Props) {
  return (
    <section>
      <header className="row">
        <h1>Exception queue</h1>
        <nav aria-label="Queue filter">
          {(["open", "resolved"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={status === s}
              onClick={() => onStatusChange(s)}
            >
              {s}
            </button>
          ))}
        </nav>
      </header>
      {exceptions.length === 0 ? (
        <p>No {status} exceptions.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Subject</th>
              <th>Ruleset</th>
              <th>Stage</th>
              <th>Rule</th>
              <th>Reason</th>
              <th>Opened</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {exceptions.map((e) => (
              <tr key={e.id}>
                <td>{e.subject_reference}</td>
                <td>
                  {e.ruleset} v{e.version}
                </td>
                <td>{e.stage}</td>
                <td>
                  <code>{e.rule}</code>
                </td>
                <td>{e.reason}</td>
                <td>{new Date(e.opened_at).toLocaleString()}</td>
                <td>
                  <button type="button" onClick={() => onOpen(e.id)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
