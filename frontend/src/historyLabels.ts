import type { Dataset, Job } from "./api";
export const jobLabels: Record<Job["kind"], string> = {
  LIST_WORKSHEETS: "Read Excel worksheets", DIAGNOSTIC: "Infrastructure check", CONNECT_S3: "S3 connection", IMPORT_DATASET: "File import",
  REPLACE_TEXT: "Text replacement", GENERATE_RULE: "Regex generation", APPLY_RULE: "Regex transformation",
  PREVIEW_TRANSFORM: "Transformation preview", APPLY_TRANSFORM: "Column transformation", EXPORT_CSV: "CSV export",
};
export const datasetLabel = (dataset: Dataset) => dataset.metadata.operation === "date_normalize" ? "Dates result"
  : dataset.metadata.operation === "categorize" ? "Category result" : dataset.metadata.operation === "regex_replace" ? "Regex result"
    : dataset.parent_id ? "Text replacement" : "Imported";
export const jobDataset = (job: Job): string | null => job.status !== "SUCCESS" || job.dataset_available === false ? null : job.dataset_id
  || (typeof job.result.source_dataset_id === "string" ? job.result.source_dataset_id : null);
export const timeLabel = (value: string) => new Date(value).toLocaleString();
