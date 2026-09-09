import { useState, type FormEvent } from "react";
import type { Resolution } from "../api";

interface Props {
  onResolve(resolution: Resolution): Promise<void>;
}

function parseValues(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const pair of text.split(",")) {
    const [key, value] = pair.split("=").map((s) => s.trim());
    if (key && value !== undefined && value !== "") values[key] = value;
  }
  return values;
}

export function ResolveForm({ onResolve }: Props) {
  const [action, setAction] = useState<Resolution["action"]>("override");
  const [resolvedBy, setResolvedBy] = useState("");
  const [note, setNote] = useState("");
  const [values, setValues] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resolution: Resolution = { action, resolved_by: resolvedBy, note };
      const parsed = parseValues(values);
      if (Object.keys(parsed).length) resolution.values = parsed;
      await onResolve(resolution);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label="Resolve exception">
      <h3>Resolve</h3>
      <fieldset>
        <legend>Action</legend>
        <label>
          <input
            type="radio"
            name="action"
            value="override"
            checked={action === "override"}
            onChange={() => setAction("override")}
          />
          Override the rule and continue
        </label>
        <label>
          <input
            type="radio"
            name="action"
            value="decline"
            checked={action === "decline"}
            onChange={() => setAction("decline")}
          />
          Decline
        </label>
      </fieldset>
      <label>
        Resolved by
        <input value={resolvedBy} onChange={(e) => setResolvedBy(e.target.value)} required />
      </label>
      <label>
        Note
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {action === "override" && (
        <label>
          Values the rule should decide, as key=value pairs
          <input
            value={values}
            onChange={(e) => setValues(e.target.value)}
            placeholder="rate=0.03"
          />
        </label>
      )}
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy}>
        {busy ? "Resolving" : "Resolve"}
      </button>
    </form>
  );
}
