import { useEffect, useReducer, useState } from "react";
import { api, ApiError } from "./api";
import { listReducer, readSaved, restoreList, save } from "./listState";

export function useCursorList<T>(resource: "jobs" | "datasets", defaults: Record<string, string>, refreshKey: string) {
  const storageKey = `patternworks-${resource}-list-v1`;
  const [state, dispatch] = useReducer(listReducer, undefined, () => restoreList(readSaved(storageKey), defaults));
  const [items, setItems] = useState<T[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, bump] = useReducer((value: number) => value + 1, 0);
  const query = new URLSearchParams({ ...state.filters, cursor: state.cursors[state.page], limit: "10" }).toString();
  useEffect(() => { save(storageKey, JSON.stringify(state)); }, [state, storageKey]);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true); setError(""); setItems([]); setNext(null);
    api<{ jobs?: T[]; datasets?: T[]; next_cursor: string | null }>(`/${resource}/?${query}`, undefined, controller.signal)
      .then((result) => { if (alive) { setItems(result[resource] || []); setNext(result.next_cursor); } })
      .catch((err) => {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 400 && state.page > 0) {
          setNotice("The saved page is no longer valid. Showing the first page."); dispatch({ type: "first" });
        } else setError(err instanceof Error ? err.message : "Could not load the list.");
      }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; controller.abort(); };
  }, [resource, query, revision, refreshKey]);
  return { state, items, next, loading, error, notice,
    filter(values: Record<string, string>) { setNotice(""); dispatch({ type: "filter", values }); },
    previous() { dispatch({ type: "previous" }); },
    advance() { if (next) dispatch({ type: "next", cursor: next }); },
    reload() { bump(); },
    refresh() { setNotice(""); dispatch({ type: "first" }); bump(); } };
}
