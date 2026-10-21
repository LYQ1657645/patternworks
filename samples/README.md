# S3 smoke-test samples

Upload `contacts.csv` and `contacts.xlsx` into the same private S3 test bucket. Both contain the same eight fictional records, with a header in the first row. The Excel worksheet is named `Contacts`.

The examples include a missing email, intentionally invalid email text, multiple emails in a note, a quoted CSV comma, date strings in several formats, and country-name variants. They support later regex replacement, date normalization and category-mapping checks. Dates are deliberately raw text rather than Excel date serials.

All names and email addresses are synthetic. These tiny files verify connectivity and parsing only; they are not evidence of large-dataset performance.
