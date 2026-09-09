import { useCallback, useEffect, useState } from "react";
import { createApi, type Api, type ExceptionDetail, type ExceptionSummary, type Resolution } from "./api";
import { ExceptionDetailView } from "./components/ExceptionDetailView";
import { ExceptionList } from "./components/ExceptionList";

type Status = "open" | "resolved";

export function App({ api = createApi() }: { api?: Api }) {
  const [status, setStatus] = useState<Status>("open");
  const [exceptions, setExceptions] = useState<ExceptionSummary[]>([]);
  const [selected, setSelected] = useState<ExceptionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setExceptions(await api.listExceptions(status));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [api, status]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function open(id: number) {
    setError(null);
    try {
      setSelected(await api.getException(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function resolve(resolution: Resolution) {
    if (!selected) return;
    setSelected(await api.resolveException(selected.id, resolution));
    await refresh();
  }

  return (
    <main>
      {error && <p role="alert">{error}</p>}
      {selected ? (
        <ExceptionDetailView
          exception={selected}
          onBack={() => setSelected(null)}
          onResolve={resolve}
        />
      ) : loading ? (
        <p>Loading</p>
      ) : (
        <ExceptionList
          exceptions={exceptions}
          status={status}
          onStatusChange={setStatus}
          onOpen={open}
        />
      )}
    </main>
  );
}
