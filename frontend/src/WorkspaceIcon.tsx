type IconName = "grid" | "source" | "history" | "table" | "arrow" | "shield";

const paths: Record<IconName, string> = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  source: "M20 7c0 2.2-3.6 4-8 4S4 9.2 4 7s3.6-4 8-4 8 1.8 8 4Z M4 7v10c0 2.2 3.6 4 8 4s8-1.8 8-4V7 M4 12c0 2.2 3.6 4 8 4s8-1.8 8-4",
  history: "M3 11a9 9 0 1 1 2.6 7.4 M3 4v7h7 M12 7v5l3 2",
  table: "M3 4h18v16H3z M3 9h18 M9 9v11",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  shield: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z M8 12l3 3 5-6",
};

export default function WorkspaceIcon({ name }: { name: IconName }) {
  return <svg className="workspace-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={paths[name]} />
  </svg>;
}
