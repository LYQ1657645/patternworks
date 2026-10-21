export const pages = {
  sources: { title: "Sources", heading: "Bring it", accent: "together.", description: "Connect your S3 bucket. Choose a file to begin.", icon: "source" },
  datasets: { title: "Datasets", heading: "Every version.", accent: "Intact.", description: "Your sources and results, kept together.", icon: "table" },
  transform: { title: "Transform", heading: "Find the", accent: "pattern.", description: "Preview your changes. Create a new dataset.", icon: "grid" },
  history: { title: "History", heading: "Work in", accent: "motion.", description: "Follow your tasks. Pick up where you left off.", icon: "history" },
} as const;
export type WorkspacePage = keyof typeof pages;
export function pageFromHash(hash: string): WorkspacePage {
  const key = hash.replace(/^#\/?/, "");
  return Object.prototype.hasOwnProperty.call(pages, key) ? key as WorkspacePage : "sources";
}
