# Daily District Reporting & Excel Automation System

Paste the day's statistics as plain text → review the extracted table → confirm → download an Excel
file identical in layout to your existing `25-11-2026_same_day_only.xlsx`.

Stack: Python · Django · SQLite (PostgreSQL optional) · Bootstrap 5 · Chart.js · Pandas + OpenPyXL.
(Django REST Framework was not needed, so it is not included.)

---------------------------------------------------------------------------------------------------

## 1. What was learned from your reference workbook

These facts were read from the file itself and drive the export:

| Item | Reference file | How the app handles it |
|---|---|---|
| Sheet | one sheet, `Sheet1` | same name |
| Columns | `Sr, District, Date, added, Released, deported, DEPORATEDION UNDER PROCESS, Retuned, Arrested by LEA` | headers copied exactly, including the legacy spellings |
| Districts | **38**, fixed order (e.g. `Muree`, `Kot Addu`, `Toba Tek Singh` after Sialkot) | stored as the district master list in that order |
| Date cells | **text** `25-11-2026` (number format `dd-mm-yyyy`) | exported the same way |
| Totals row | none | none (optional switch `EXPORT_INCLUDE_TOTALS_ROW` in `config/settings.py`) |
| Header style | bold white on green `228B22`, centred, thin borders | reproduced; body cells get consistent borders/alignment (the reference body styling is uneven) |

The reference file's own figures (Located 23, Released 2, Under Process 28, others 0) are exactly what
your example text produces, so the automated tests compare the generated workbook to the reference
**cell by cell**.

**Category mapping** (as requested): Located→`added`, Released→`Released`, Deported→`deported`,
UnderProcess→`DEPORATEDION UNDER PROCESS`, Returned→`Retuned`, Taken by LEA→`Arrested by LEA`.
The LEA mapping starts **unconfirmed**: figures cannot be saved into that column until an administrator
clicks *Confirm mapping* in **Settings** (a one-time step; the all-zero case is never blocked).

---------------------------------------------------------------------------------------------------

## 2. Installation on Windows (step by step)

1. **Install Python 3.10 or newer** from <https://www.python.org/downloads/>. On the first installer
   screen tick **"Add python.exe to PATH"**.
2. Unzip the project, e.g. to `C:\daily_report_system`.
3. Open **Command Prompt** (cmd) and run:

```bat
cd C:\daily_report_system
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

   (In PowerShell use `venv\Scripts\Activate.ps1`; if Windows blocks it run
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. Command Prompt avoids this.)

4. **Create the database tables.** The migration files are generated on your machine so they always
   match your Django version:

```bat
python manage.py makemigrations reports
python manage.py migrate
```

5. **Load the district list, categories and the Editors group** (safe to repeat):

```bat
python manage.py seed_master_data
```

6. **Create your administrator login:**

```bat
python manage.py createsuperuser
```

7. **Run the automated tests** (do this once after installing):

```bat
python manage.py test
```

8. **Start the application:**

```bat
python manage.py runserver
```

   Open <http://127.0.0.1:8000/> and sign in. Stop the server with `Ctrl+C`.
   Next time you only need: `cd C:\daily_report_system` → `venv\Scripts\activate` → `python manage.py runserver`.

9. In the app: **Settings → Confirm mapping** for *Taken by LEA → Arrested by LEA* when you are happy with it.

Bootstrap and Chart.js are loaded from a CDN, so the browser needs internet access for styling and charts.

---------------------------------------------------------------------------------------------------

## 3. Daily workflow

1. **New Daily Report** → paste the text (the date can be inside the text or typed in the date box).
2. **Process Report** (or *Preview Data*) → the editable preview opens. *Validate Data* only shows the checks
   without leaving the page. Nothing is saved yet.
3. Review the table. Fix any highlighted cell, the declared totals, or assign unrecognised lines to a district,
   then press **Re-validate**. Column sums are shown live under the table next to the declared totals.
4. When the banner says *Ready to save*: **Confirm & Save**, or **Confirm & Download Excel**.
5. The saved report page shows the figures, revision history and the original text. Past reports can be
   downloaded again at any time as Excel.

If a report for that date already exists you must tick *authorised correction* and give a reason; the old figures
are kept in the revision history.

### Accepted text format
```
24-11-2026

Located Total: 23
Rawalpindi: 1
Chakwal: 5
Gujranwala: 17

Released Total: 2
Attock: 02

Deported Total: 0
Taken by LEA: 0
UnderProcess: 28
Attock: 7
Gujrat: 19
T.T.Singh: 2
```
Blank lines, extra spaces, trailing full stops, a missing colon, capitals, bullets and `Date:` prefixes are tolerated.
Variants such as `T.T. Singh` / `Toba Tek Singh`, `Under Process` / `UnderProcess` are recognised. More spellings can be
added per district in the admin site (**District → aliases**). Dates are read as **DD-MM-YYYY**. Categories not
supplied count as 0.

### Validation rules (accuracy first - the app never changes a number for you)
* Date must be a real date; text date and form date must agree.
* Values must be whole numbers, never negative; declared totals too.
* Every district name must match the master list. Close misspellings are accepted only when unambiguous and are
  always flagged with a warning. Unknown names must be assigned to a district or explicitly discarded.
* Duplicate districts inside a category, a district without a number, or a negative value leave the cell **empty and
  flagged** so you enter the right figure; the parser never picks one for you.
* Declared category total must equal the sum of its districts (otherwise saving is blocked).
* Heading missing twice, values before any heading, or no headings at all: fix the text and process again.
* The server re-validates everything on save; a report with errors cannot be stored or exported.

---------------------------------------------------------------------------------------------------

## 4. Users and roles
* **Admin** (superuser): everything, plus Settings actions and the admin site (`/admin/`).
* **Editors** (group): create and revise reports. Add a user in `/admin/` → Users → Groups → *Editors*.
* **Everyone else**: read-only (dashboard, history, statistics, comparison, Excel downloads).

Passwords are hashed (PBKDF2), forms are CSRF-protected, sessions expire after 12 hours, and every report
creation/revision and mapping confirmation is written to `logs/app.log`.

---------------------------------------------------------------------------------------------------

## 5. Useful commands

```bat
python manage.py test                                 :: all automated tests
python manage.py import_text sample_data\example_valid.txt --dry-run
python manage.py import_text old1.txt old2.txt        :: bulk-import historical text files (same validation)
python manage.py backup_data                          :: JSON dump (+ SQLite file copy) into backups\
```

### Backup and recovery
* `backup_data` writes `backups\backup_<time>.json` (all reports, users, groups) and, on SQLite, `db_<time>.sqlite3`.
  The newest 30 of each are kept (`--keep N` to change).
* **Daily automatic backup** (Windows Task Scheduler), adjust the paths:
```bat
schtasks /create /sc daily /st 23:30 /tn "DDR Backup" /tr "C:\daily_report_system\venv\Scripts\python.exe C:\daily_report_system\manage.py backup_data"
```
* **Restore (SQLite file):** stop the server, copy a `db_<time>.sqlite3` over `db.sqlite3`.
* **Restore (JSON, any database):** on a fresh database run `python manage.py migrate`, then
  `python manage.py loaddata backups\backup_<time>.json` (do *not* run `seed_master_data` first; the backup contains it).
* **PostgreSQL:** also use `pg_dump -U <user> <dbname> > backup.sql`.

### Switching to PostgreSQL
Install PostgreSQL, create a database, uncomment `psycopg[binary]` in `requirements.txt`, `pip install -r requirements.txt`,
then set these variables before running (cmd): `set DB_ENGINE=postgres`, `set DB_NAME=daily_reports`, `set DB_USER=postgres`,
`set DB_PASSWORD=...`, `set DB_HOST=127.0.0.1`. Then `migrate` and `seed_master_data` again. For real use also set
`DJANGO_DEBUG=0`, a long `DJANGO_SECRET_KEY`, and `HTTPS=1` once served over HTTPS.

---------------------------------------------------------------------------------------------------

## 6. Project structure

```
manage.py, requirements.txt, README.md
config/                     settings, urls, wsgi/asgi
reports/
  core/                     pure Python, no Django: the heart of the system
    constants.py              reference districts, categories, Excel layout facts
    parser.py                 text -> structured data + issues
    validator.py              totals / numbers / date checks
    excel.py                  OpenPyXL + Pandas export matching the reference
  models.py                 District, ReportCategory, DailyReport, DistrictReportDetail, ReportRevision
  services.py               draft handling, saving with revisions, export glue
  analytics.py              dashboard / statistics / comparison queries
  views.py, urls.py, permissions.py, admin.py, context_processors.py
  management/commands/      seed_master_data, import_text, backup_data
  templates/, static/       Bootstrap 5 UI, Chart.js charts, live-sum JavaScript
  tests/                    test_parser, test_validator, test_excel, test_django
sample_data/                reference_template.xlsx, example inputs (valid, messy, invalid), example_output
```

### Database
`District` 1─* `DistrictReportDetail` *─1 `ReportCategory`; `DailyReport` 1─* `DistrictReportDetail`;
`DailyReport` 1─* `ReportRevision`; users = Django's `auth.User`. One detail row per
(report, district, category) incl. zeros - enforced by a unique constraint; values are `PositiveIntegerField`
(database check against negatives); one report per date (unique). Indexes on (district, category) and (category, report)
keep per-district history and comparisons fast over years of data. The original text is kept on `DailyReport.raw_text`
and each save stores a full snapshot in `ReportRevision`.

---------------------------------------------------------------------------------------------------

## 7. Testing status (please read)

* **Verified while building** (run in the build environment, 43 tests): the text parser, the validator and the Excel
  exporter. Includes: your example text (and a messy variant) parsed to identical results; every spelling variant;
  duplicates, unknown names, negatives, bad/missing/conflicting dates; and the generated workbook compared
  **cell by cell** with `25-11-2026_same_day_only.xlsx` (values, 38 districts and order, text dates, header styling,
  column widths). Command: `python -m unittest reports.tests.test_parser reports.tests.test_validator reports.tests.test_excel`
* **Written but not executed during the build**: the Django layer (models, views, templates, commands) and its tests in
  `reports/tests/test_django.py` (storage, revisions, permissions, full paste→preview→save→download flow, history filters,
  comparison). Django could not be installed in the build environment (no network), so this layer was only syntax- and
  name-checked. **Run `python manage.py test` first** after installing; if anything fails, send me the output and I will
  fix it. Migrations are generated by `makemigrations` on your machine for the same reason.

## 8. Troubleshooting
* `python` not recognised → reinstall Python with "Add to PATH", or use `py` instead of `python`.
* Styling/charts missing → the browser cannot reach the CDN (jsdelivr.net).
* "Master-list problem: Spelling ... is ambiguous" → two districts/categories share an alias; fix it in `/admin/`.
* Forgot password → `python manage.py changepassword <username>`.
