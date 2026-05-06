# 🌿 MindBridge Campus — Mental Health Platform

> A full-stack Django web app where **ALL database logic is written in pure SQL and
> Procedural Logic (PL)**. Django is used only as a web framework — for routing,
> sessions, and HTML templating. Zero ORM.

---

## Quickstart

```bash
pip install django
python manage.py migrate
python manage.py runserver
# Open http://127.0.0.1:8000
```

All tables, seed data, procedures, and triggers run automatically on first start.

---

## Test Accounts (password: `password`)

| Email | Role |
|---|---|
| arjun@student.edu | Student |
| meera@student.edu | Student |
| rohan@student.edu | Student |
| priya@campus.edu | Counsellor |
| rahul@campus.edu | Counsellor |
| ananya@campus.edu | Counsellor |
| vikram@campus.edu | Counsellor |

---

## Client Configuration Guide

Everything a client needs to customise lives in **one file**: `core/sql_engine.py`

### Add a new counsellor
Edit the `SEED_SQL` block — add a row to the `counsellor` INSERT:
```sql
('Dr. New Name', 'new@campus.edu', '+91 ...', '<sha256_of_password>',
 'Specialization', 8, 'Bio text here.', 1, 25),
```
The password hash is SHA-256 of their password. Generate it at https://emn178.github.io/online-tools/sha256.html

### Add a new diagnosis category
```sql
INSERT INTO diagnosis_category(name, description) VALUES
('Sleep Disorders', 'Insomnia, hypersomnia, circadian rhythm issues');
```

### Add recommendations for a category
```sql
INSERT INTO recommendation(category_id, title, body, resource_link, priority) VALUES
(9, 'Sleep Hygiene Checklist', 'Keep a fixed sleep schedule...', NULL, 1);
```

### Change institution name / branding
Edit the `<title>` in `templates/base.html` and the footer text.

---

## SQL/PL Architecture (`core/sql_engine.py`)

### Section 1 — DB Connection
Raw `sqlite3` connection. Every query goes through `DB()`.

### Section 2 — DDL (Schema)
`SCHEMA_SQL` string — all `CREATE TABLE IF NOT EXISTS` statements.
Tables: `student`, `counsellor`, `diagnosis_category`, `recommendation`,
`appointment`, `session`, `audit_log`, `notification`.

### Section 3 — DML (Seed Data)
`SEED_SQL` string — all `INSERT OR IGNORE` statements for initial data.
Clients replace this with their own counsellors, categories, and recommendations.

### Section 4 — Stored Procedures (PL)
| Function | Equivalent to |
|---|---|
| `sp_register_student()` | `CREATE PROCEDURE sp_register_student` |
| `sp_login()` | `CREATE PROCEDURE sp_login` |
| `sp_book_appointment()` | `CREATE PROCEDURE sp_book_appointment` |
| `sp_cancel_appointment()` | `CREATE PROCEDURE sp_cancel_appointment` |
| `sp_complete_session()` | `CREATE PROCEDURE sp_complete_session` |
| `sp_submit_feedback()` | `CREATE PROCEDURE sp_submit_feedback` |

Each procedure: validates input → runs SQL → fires triggers → writes audit log → commits or rolls back.

### Section 5 — Triggers (PL)
| Function | Fires when |
|---|---|
| `_trigger_welcome_notification()` | After student INSERT |
| `_trigger_notify()` | After booking / cancel / completion |
| `_audit()` | After every write operation |

### Section 6 — View Queries (SQL VIEWs)
| Function | Equivalent to |
|---|---|
| `view_student_dashboard()` | `CREATE VIEW v_student_dashboard` |
| `view_counsellor_dashboard()` | `CREATE VIEW v_counsellor_dashboard` |
| `view_recommendations_for_student()` | `CREATE VIEW v_student_recommendations` |
| `view_all_counsellors()` | `CREATE VIEW v_counsellors_public` |
| `view_appointment_detail()` | `CREATE VIEW v_appointment_detail` |

### Section 7 — init_db()
Runs DDL + DML on startup. Safe to call multiple times.

---

## Recommendation Engine (pure SQL)

```sql
SELECT DISTINCT r.rec_id, r.title, r.body, r.priority, d.name AS category_name
FROM   recommendation     r
JOIN   diagnosis_category d  ON d.category_id      = r.category_id
JOIN   session            se ON se.diagnosis_category = r.category_id
JOIN   appointment        a  ON a.appointment_id   = se.appointment_id
WHERE  a.student_id = :student_id AND a.status = 'completed'
ORDER  BY r.priority ASC, MAX(a.apt_date) DESC
```

This query joins the student's completed sessions → their diagnoses → the
recommendation table. Result: personalised, priority-ranked recommendations
auto-generated from whatever the counsellor diagnosed.

