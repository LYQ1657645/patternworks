# S3 smoke-test samples

Upload `contacts.csv` and `contacts.xlsx` into the same private S3 test bucket. Both contain the same eight fictional records, with a header in the first row. The Excel worksheet is named `Contacts`.

The examples include a missing email, intentionally invalid email text, multiple emails in a note, a quoted CSV comma, date strings in several formats, and country-name variants. They support later regex replacement, date normalization and category-mapping checks. Dates are deliberately raw text rather than Excel date serials.

All names and email addresses are synthetic. These tiny files verify connectivity and parsing only; they are not evidence of large-dataset performance.

`demo-contacts-60.csv` is a separate fictional recording fixture with the same six-column schema. It contains sixty unique contact IDs, repeated mixed date formats and country aliases, blank/invalid emails, multi-email notes and quoted commas. Upload it to your own test bucket before recording; the app's default 25-row pages will contain 25, 25 and 10 rows. It is a usability/pagination fixture, not a performance benchmark. See [recording guide](../docs/DEMO_RECORDING_GUIDE_ZH.md).
