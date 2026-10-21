export type ListState = { filters: Record<string, string>; cursors: string[]; page: number };
export type ListAction = { type: "filter"; values: Record<string, string> } | { type: "next"; cursor: string }
  | { type: "previous" } | { type: "first" };

export function listReducer(state: ListState, action: ListAction): ListState {
  if (action.type === "filter") return { filters: { ...state.filters, ...action.values }, cursors: [""], page: 0 };
  if (action.type === "first") return { ...state, cursors: [""], page: 0 };
  if (action.type === "previous") return { ...state, page: Math.max(0, state.page - 1) };
  return { ...state, cursors: [...state.cursors.slice(0, state.page + 1), action.cursor], page: state.page + 1 };
}

export function restoreList(raw: string | null, defaults: Record<string, string>): ListState {
  const fresh = { filters: defaults, cursors: [""], page: 0 };
  try {
    const saved = JSON.parse(raw || "null");
    if (!saved || !Array.isArray(saved.cursors) || saved.cursors[0] !== "" ||
      saved.cursors.some((c: unknown) => typeof c !== "string" || c.length > 2048) ||
      !Number.isInteger(saved.page) || saved.page < 0 || saved.page >= saved.cursors.length ||
      !saved.filters || Object.keys(defaults).some((key) => typeof saved.filters[key] !== "string" || saved.filters[key].length > 256)) return fresh;
    return { filters: Object.fromEntries(Object.keys(defaults).map((key) => [key, saved.filters[key]])), cursors: saved.cursors, page: saved.page };
  } catch { return fresh; }
}

export function readSaved(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}
export function save(key: string, value: string) {
  try { sessionStorage.setItem(key, value); } catch { /* Storage is optional. */ }
}
export function savedId(key: string): string | null {
  const id = readSaved(key);
  return id && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(id) ? id : null;
}
