# Patternworks demo narration

Read the numbered paragraphs aloud. The headings are editing cues, not spoken text. The matching clicks and checkpoints are in [the recording guide](DEMO_RECORDING_GUIDE_ZH.md). Recommended edited length: about 6–7 minutes, depending on speaking pace and actual task duration.

## 01 Introduction

Hi, I'm Yingqi. This is Patternworks, a web application for transforming tabular data with natural language. I'll connect my own Amazon S3 bucket, replace email addresses, normalize dates, classify country values, and download the result.

## 02 Connect to S3

I enter my bucket name, region, and read-only AWS credentials. Both credential fields are masked. The credentials are encrypted on the server and expire after one hour. After the connection succeeds, the application shows the files available in my bucket.

## 03 Select and import a file

The application supports CSV and Excel. Selecting an Excel file discovers its worksheets automatically. For this walkthrough, I'll import a CSV with sixty fictional contacts, so I can also show pagination. The import runs in the background, with its progress displayed here.

## 04 Inspect the original data

The data contains email addresses, mixed date formats, and different names for the same country. Some email values are blank or deliberately invalid. Results load in pages of twenty-five rows. Here, the second page starts at row twenty-six.

## 05 Generate and review a regex

I select Email and Notes, describe the pattern as “Find email addresses,” and enter a replacement value. Generate creates a validated rule and a sample preview. It has not changed the dataset yet. I can inspect the expression and compare the original and replacement values in both columns.

## 06 Change the preview and show caching

If I change the replacement, Apply becomes unavailable until I update the preview. This prevents applying an outdated preview. The description is unchanged, so the validated pattern can be reused from Redis. The rule details confirm that this request used the cache without another model call.

## 07 Apply and inspect the result

Now I apply the rule. Django submits the job, Celery runs the work, and Spark processes the selected columns. Tasks shows its progress and completion. The result is saved as a separate version. Email addresses are replaced in both columns, while blank values, unmatched text, and unselected columns are preserved.

## 08 Normalize dates

The first additional LLM-assisted transformation is date normalization. I select JoinDate and allow the selected values to be processed. I preview the output, then apply it. The result adds standardized dates and a status column. The original date values remain available for comparison.

## 09 Classify country values

The second transformation is classification. I select Country, provide three categories, and choose Other as the fallback. The preview maps country-name variations to consistent labels. Applying it adds category and status columns to a new version, while preserving the original country values.

## 10 Download the final data

The final dataset has sixty rows and ten columns. Export CSV prepares a download in the background. I download and open the file to check that it includes the masked emails, normalized dates, categories, and all sixty records.

## 11 Review versions and tasks

The library connects saved versions through their transformations. I can open the original or a processed version. Tasks keeps the execution history separately, including progress, failures, cancellations, and eligible retries. The original S3 file is never overwritten.

## 12 Architecture, scale evidence, and closing

The repository includes Docker Compose, setup instructions, architecture notes, and automated checks. A separate single-server benchmark verified one million synthetic CSV rows, including exact result checks. Import took about eighty-one seconds, and regex replacement took about seventy-four. Date and category measurements used cached mappings. These results exclude S3 transfer and live model latency. The public demo and reproduction details are linked in the README. Thank you.

## Optional narration for an existing completed cancellation and retry demonstration

Use this only if the matching actions are actually recorded. It is not part of the main narration.

I cancel this running task. It remains in history as cancelled. Retry creates a new task, and the original cancellation record is preserved. The new task completes and saves its own result.

## Optional narration for an actual retryable failure

Use this only when the displayed error allows Retry and the required recovery has actually been completed. Do not describe a corrected new import as retrying the original task.

This task failed with a clear error message. After resolving the cause, I retry it as a new task. The failed record stays in history, and the new attempt completes successfully.

## Short pronunciation notes

| Term | Reading cue |
| --- | --- |
| Patternworks | PAT-ern-works |
| S3 | S three |
| AWS | A W S |
| CSV | C S V |
| Django | JANG-go |
| Celery | SELL-er-ee |
| Redis | RED-iss |
| PySpark | pie-spark |
| regex | REG-ex |
| asynchronous | ay-SINK-ruh-nus |
| pagination | paj-ih-NAY-shun |

You do not need to read the regex symbols, UUIDs, URLs, or every category name aloud.
