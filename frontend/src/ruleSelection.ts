export function toggleColumn(all: string[], selected: string[], key: string, checked: boolean): string[] {
  const next = new Set(selected);
  if (checked) next.add(key);
  else next.delete(key);
  return all.filter((column) => next.has(column));
}

export function sameColumns(first: string[], second: string[]): boolean {
  return first.length === second.length && first.every((column) => second.includes(column));
}
