# Patternworks demo narration

Simple, workflow-first version. Read only the paragraphs under 01–12 aloud. Matching actions are in [the recording guide](DEMO_RECORDING_GUIDE_ZH.md). Allow about 5–6 minutes for narration and clicks, plus task waiting time. Read result sentences only after the results appear. Updated 22 October 2026.

## 01 Introduce the website

Hi, I'm Yingqi. This is Patternworks. It helps users clean and transform table data using plain language. I'll show the full workflow: connect a file, preview changes, apply them, and download the result.

## 02 Connect to S3

First, I enter my own S3 bucket name, region, and AWS credentials. The keys stay hidden on screen and are encrypted on the server. I click Connect bucket. Here are the files in my bucket.

## 03 Choose and import a file

Patternworks supports CSV and Excel. For Excel, I can select a worksheet from this list. For this demo, I'll import a CSV with sixty sample contacts. The import runs in the background, and I can follow its progress.

## 04 Review the data

Here is the original data. It has email addresses, mixed date formats, and different names for the same country. The table loads one page at a time. Next takes me to row twenty-six. Now I'll select Transform.

## 05 Describe a replacement

I select Email and Notes. I type “Find email addresses” and enter the replacement text. Generate creates a regex rule, checks it, and shows a preview. I can compare the changes in both columns. The data has not changed yet.

## 06 Check the updated preview

I'll change the replacement to EMAIL in brackets. I need to update the preview before I can apply it. Since the description is the same, this request reuses a cached rule without another AI call.

## 07 Apply and follow the task

Now I click Apply. The work runs in the background. In Tasks, I can see its progress and when it finishes. Here is the result: emails are replaced in both columns. The application saves a new version and keeps the original.

## 08 Standardize dates

There are also two extra AI transformations. The first standardizes dates. I select JoinDate, allow the selected values to be sent to OpenAI, and set a request limit. I preview the changes, check the estimate, and apply. The new date column uses one format. The original dates stay available.

## 09 Group country names

The second transformation groups values into categories. I select Country and define United States, Australia, and Other. I preview the results and apply. USA and U.S. now map to United States. The earlier email and date changes are also kept in this version.

## 10 Download the result

The final version has sixty rows and ten columns. I click Export CSV, wait for it to finish, and download the file. Here it is, with the email replacements, standard dates, and country categories.

## 11 Explain versions and tasks

In the library, each planet represents a different saved version. The lines show how the versions are connected. I can open an earlier version here. Tasks keeps the operation history, with cancel and retry available for eligible tasks. The source file in S3 stays unchanged.

## 12 Explain the implementation and close

The interface uses React, with Django on the server. Celery runs background tasks. Redis supports the task queue and caches repeated requests. PySpark processes data across partitions.

The repository includes Docker Compose setup, tests, monitoring instructions, and million-row test reports. The large tests use simulated or cached AI results, so they test the data pipeline, not live AI speed. The README explains the setup and trade-offs. That's the workflow, from S3 to a downloaded result. Thank you.

---

## Recording notes — do not read aloud

- **06:** Say “reuses a cached rule” only when Rule details confirms a cache hit. Otherwise replace that last sentence with: “I check the new preview before applying the change.” The actual input is `[EMAIL]`; brackets are ordinary replacement text, not required syntax.
- **08–09:** Use the actual request estimate and remaining budget. Raise the budget if needed before Apply. Do not claim the limit is a dollar amount or that every run uses exactly one request.
- **10:** Open this run's downloaded file and check the final record, ID 60. Only state sixty rows and ten columns when the actual result matches.
- **11:** Mention cancel and retry while showing Tasks. An actual cancellation or failure demonstration can be recorded separately; do not describe one as completed unless shown.
- **12:** Show the README architecture, Compose setup, automated checks, and linked scale report. The report distinguishes real parsing/Spark/export from simulated or cached model results. Do not describe a multi-machine deployment or a live million-row AI benchmark.
- **Required video evidence:** Record your own masked S3 credential entry and a successful connection. Keep at least one real asynchronous task visible from submission to completion. The final video must be embedded in README; this draft does not complete that submission step.
- **Optional Replace text:** No extra scene is needed. If asked: “Replace text replaces exact text, such as USA with US, without AI.”

## Optional cancellation and retry narration

Read only if the corresponding actions are recorded:

I cancel this task. Its cancelled record stays in history. Retry starts a new task. This attempt finishes successfully.

For a real retryable failure, after resolving its cause:

This task failed with an error message. I retry it as a new task. The new attempt finishes, and the failed record stays in history.

## Pronunciation

| Term | Reading cue |
| --- | --- |
| Patternworks | PAT-ern-works |
| S3 | S three |
| Django | JANG-go |
| Celery | SELL-er-ee |
| Redis | RED-iss |
| PySpark | pie-spark |
| regex | REG-ex |

Do not read regex symbols, IDs, URLs, or test counts aloud.
