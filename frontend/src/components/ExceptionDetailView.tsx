import type { ExceptionDetail, Resolution } from "../api";
import { DecisionRecordView } from "./DecisionRecordView";
import { ResolveForm } from "./ResolveForm";

interface Props {
  exception: ExceptionDetail;
  onBack(): void;
  onResolve(resolution: Resolution): Promise<void>;
}

export function ExceptionDetailView({ exception, onBack, onResolve }: Props) {
  return (
    <article>
      <button type="button" onClick={onBack}>
        Back to queue
      </button>
      <h1>
        {exception.subject_reference}: {exception.reason}
      </h1>
      <p>
        <span className={`status ${exception.status}`}>{exception.status}</span> at{" "}
        {exception.stage}, raised by <code>{exception.rule}</code>
        {exception.resolved_by ? `, resolved by ${exception.resolved_by}` : ""}
      </p>
      {exception.history.length > 0 && (
        <section aria-label="History">
          <h3>History</h3>
          <ul>
            {exception.history.map((h, i) => (
              <li key={i}>
                {new Date(h.at).toLocaleString()}: {h.by} chose to {h.action}{" "}
                <code>{h.rule_name}</code>
                {h.note ? ` (${h.note})` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}
      <DecisionRecordView record={exception.record} />
      {exception.status === "open" && <ResolveForm onResolve={onResolve} />}
    </article>
  );
}
