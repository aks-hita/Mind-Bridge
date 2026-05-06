"""
================================================================================
  MINDBRIDGE CAMPUS — SQL/PL ENGINE
  ─────────────────────────────────
  ALL database logic lives here as raw SQL and PL (Procedural Logic).
  Django is used ONLY as a web framework (routing, sessions, templating).
  No Django ORM queries are used anywhere in this file or the views.

  Structure:
    1. DB()           — raw connection helper
    2. Schema SQL     — CREATE TABLE statements (DDL)
    3. Seed SQL       — INSERT statements (DML)
    4. Stored PL      — Python functions that emulate stored procedures
                        using raw SQL + procedural logic
    5. Trigger PL     — Functions that fire automatically on certain events
    6. View SQL       — Named SELECT queries (like DB views)
    7. Public API     — The interface views.py calls
================================================================================
"""

import sqlite3
import hashlib
import os
import json
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / 'mindbridge.db'


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — DATABASE CONNECTION HELPER
# ══════════════════════════════════════════════════════════════════════════════

def DB():
    """
    Opens a raw SQLite connection with row_factory so rows behave like dicts.
    Every query in this system goes through this connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # rows accessible as row['col_name']
    conn.execute("PRAGMA foreign_keys = ON") # enforce FK constraints
    conn.execute("PRAGMA journal_mode = WAL") # better concurrency
    return conn


def _hash(password: str) -> str:
    """Simple SHA-256 password hash. In production use bcrypt."""
    return hashlib.sha256(password.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — DDL: CREATE TABLE STATEMENTS
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """

-- ─────────────────────────────────────────
-- TABLE: student
-- Stores all student (patient) accounts.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS student (
    student_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    phone           TEXT,
    password_hash   TEXT    NOT NULL,
    gender          TEXT    CHECK(gender IN ('Male','Female','Other')),
    dob             TEXT,
    department      TEXT,
    year_of_study   INTEGER CHECK(year_of_study BETWEEN 1 AND 6),
    registration_dt TEXT    DEFAULT (datetime('now')),
    is_active       INTEGER DEFAULT 1
);

-- ─────────────────────────────────────────
-- TABLE: counsellor
-- Stores counsellor accounts.
-- Admins edit this table directly to onboard new counsellors.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS counsellor (
    counsellor_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name           TEXT    NOT NULL,
    email               TEXT    NOT NULL UNIQUE,
    phone               TEXT,
    password_hash       TEXT    NOT NULL,
    specialization      TEXT    NOT NULL,
    experience_years    INTEGER DEFAULT 0,
    bio                 TEXT,
    available           INTEGER DEFAULT 1,
    max_students        INTEGER DEFAULT 20
);

-- ─────────────────────────────────────────
-- TABLE: diagnosis_category
-- Master list of mental health categories.
-- Admins can add new categories here.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS diagnosis_category (
    category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    description     TEXT
);

-- ─────────────────────────────────────────
-- TABLE: recommendation
-- Maps a diagnosis category to a set of resources/tips.
-- This is what drives the personalised student recommendations.
-- Admins can add/edit recommendations without touching code.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendation (
    rec_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id     INTEGER NOT NULL REFERENCES diagnosis_category(category_id),
    title           TEXT    NOT NULL,
    body            TEXT    NOT NULL,
    resource_link   TEXT,
    priority        INTEGER DEFAULT 1  -- 1=high, 2=medium, 3=low
);

-- ─────────────────────────────────────────
-- TABLE: appointment
-- A booking between one student and one counsellor.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS appointment (
    appointment_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id          INTEGER NOT NULL REFERENCES student(student_id),
    counsellor_id       INTEGER NOT NULL REFERENCES counsellor(counsellor_id),
    apt_date            TEXT    NOT NULL,
    apt_time            TEXT    NOT NULL,
    mode                TEXT    DEFAULT 'online' CHECK(mode IN ('online','offline')),
    status              TEXT    DEFAULT 'booked'
                                CHECK(status IN ('booked','completed','cancelled','no_show')),
    reason              TEXT,
    booking_dt          TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
-- TABLE: session
-- The actual counselling session record, created after appointment completes.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session (
    session_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id      INTEGER NOT NULL UNIQUE REFERENCES appointment(appointment_id),
    session_date        TEXT    NOT NULL,
    duration_min        INTEGER DEFAULT 60,
    notes               TEXT,
    diagnosis_category  INTEGER REFERENCES diagnosis_category(category_id),
    severity            TEXT    CHECK(severity IN ('mild','moderate','severe')),
    follow_up_needed    INTEGER DEFAULT 0,
    student_feedback    TEXT,
    student_rating      INTEGER CHECK(student_rating BETWEEN 1 AND 5)
);

-- ─────────────────────────────────────────
-- TABLE: audit_log
-- Automatic record of every key action in the system.
-- Populated by trigger-style PL functions.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,
    entity      TEXT    NOT NULL,
    entity_id   INTEGER,
    actor       TEXT,
    detail      TEXT,
    logged_at   TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
-- TABLE: notification
-- In-app notifications for students and counsellors.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notification (
    notif_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_type   TEXT    NOT NULL CHECK(user_type IN ('student','counsellor')),
    user_id     INTEGER NOT NULL,
    message     TEXT    NOT NULL,
    is_read     INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now'))
);

"""

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — DML: SEED DATA
# Clients replace these INSERT statements with their own data.
# ══════════════════════════════════════════════════════════════════════════════

SEED_SQL = """

-- ── Diagnosis categories ──────────────────────────────────────────────────
INSERT OR IGNORE INTO diagnosis_category(name, description) VALUES
('Anxiety',         'Generalised anxiety, social anxiety, panic disorders'),
('Depression',      'Major depressive disorder, dysthymia, seasonal affective'),
('Stress',          'Academic stress, burnout, exam pressure'),
('Grief',           'Loss, bereavement, life transitions'),
('Relationship',    'Family conflict, romantic issues, peer pressure'),
('Trauma',          'PTSD, childhood trauma, abuse survivors'),
('Self-Esteem',     'Body image, imposter syndrome, confidence issues'),
('Addiction',       'Substance use, gaming, social media dependency');

-- ── Recommendations per category ──────────────────────────────────────────
INSERT OR IGNORE INTO recommendation(category_id,title,body,resource_link,priority) VALUES
-- Anxiety
(1,'Deep Breathing Exercise','Practice 4-7-8 breathing: inhale 4s, hold 7s, exhale 8s. Do this 3x whenever anxious.','https://www.healthline.com/health/4-7-8-breathing',1),
(1,'Progressive Muscle Relaxation','Tense and release each muscle group from toes to head. Reduces physical symptoms of anxiety.','https://www.verywellmind.com/progressive-muscle-relaxation',1),
(1,'Limit Caffeine','Reduce coffee and energy drinks which amplify anxiety symptoms.', NULL, 2),
(1,'Journaling','Write your worries down and challenge each one with a rational counter-thought.', NULL, 2),
-- Depression
(2,'Sunlight Exposure','Spend 20–30 minutes in natural sunlight daily. Boosts serotonin naturally.', NULL, 1),
(2,'Behavioural Activation','Schedule one enjoyable activity each day even when you don''t feel like it.','https://www.psychologytools.com/resource/behavioral-activation',1),
(2,'Reach Out','Connect with one trusted friend or family member this week. Isolation worsens depression.', NULL, 1),
(2,'Sleep Hygiene','Maintain consistent sleep/wake times. Poor sleep is strongly linked to depressive episodes.', NULL, 2),
-- Stress
(3,'Time-Blocking','Divide your day into focused blocks. Use the Pomodoro technique: 25 min work, 5 min break.','https://todoist.com/productivity-methods/pomodoro-technique',1),
(3,'Physical Exercise','Even a 20-minute walk significantly reduces cortisol (the stress hormone).', NULL, 1),
(3,'Say No','Practice declining non-essential commitments to protect your energy.', NULL, 2),
-- Grief
(4,'Allow Grief','Understand that grief is not linear. Give yourself permission to feel without judgement.', NULL, 1),
(4,'Memory Rituals','Create a small ritual to honour what was lost — a photo, a journal entry, a candle.', NULL, 2),
-- Relationship
(5,'Active Listening','In conflicts, focus entirely on understanding the other person before responding.', NULL, 1),
(5,'Set Healthy Boundaries','Clearly communicate your needs and limits. Boundaries protect relationships.', NULL, 1),
-- Trauma
(6,'Grounding Technique','Use 5-4-3-2-1: name 5 things you see, 4 you hear, 3 you can touch, 2 you smell, 1 you taste.', NULL, 1),
(6,'Trauma-Informed Yoga','Gentle body movement helps release stored trauma. Look for trauma-sensitive yoga classes.', NULL, 2),
-- Self-Esteem
(7,'Affirmation Practice','Write 3 genuine things you appreciate about yourself each morning.', NULL, 1),
(7,'Celebrate Small Wins','Track daily accomplishments, no matter how small. Builds evidence of competence.', NULL, 2),
-- Addiction
(8,'Identify Triggers','Map when and why cravings occur. Awareness is the first step to change.', NULL, 1),
(8,'Replace the Habit','Substitute the addictive behaviour with a healthy coping mechanism immediately.', NULL, 1);

-- ── Counsellors ───────────────────────────────────────────────────────────
INSERT OR IGNORE INTO counsellor(full_name,email,phone,password_hash,specialization,experience_years,bio,available,max_students) VALUES
('Dr. Priya Sharma',  'priya@campus.edu',  '+91 98001 11111', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Anxiety & Depression', 9,  'Specialist in CBT for university students. Warm, non-judgmental approach.', 1, 25),
('Dr. Rahul Mehta',   'rahul@campus.edu',  '+91 98001 22222', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Trauma & PTSD',        13, 'Trained in EMDR and trauma-focused therapies. Safe space for all.', 1, 20),
('Dr. Ananya Gupta',  'ananya@campus.edu', '+91 98001 33333', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Stress & Academic Pressure', 6, 'Helps students manage burnout and build resilience.', 1, 30),
('Dr. Vikram Nair',   'vikram@campus.edu', '+91 98001 44444', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Relationship & Family', 11, 'Expert in interpersonal therapy and family systems.', 1, 20);

-- ── Students ──────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO student(full_name,email,phone,password_hash,gender,dob,department,year_of_study) VALUES
('Arjun Singh',   'arjun@student.edu',  '+91 90001 11111', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Male',   '2002-05-14', 'Computer Science', 3),
('Meera Pillai',  'meera@student.edu',  '+91 90001 22222', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Female', '2003-09-22', 'Psychology',       2),
('Rohan Das',     'rohan@student.edu',  '+91 90001 33333', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8', 'Male',   '2001-11-30', 'Engineering',      4);

"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — STORED PROCEDURES (PL)
# Python functions that bundle SQL + procedural logic, exactly like stored
# procedures in Oracle/PostgreSQL. Each is a self-contained unit of work
# with its own transaction, validation, and audit trail.
# ══════════════════════════════════════════════════════════════════════════════

def sp_register_student(full_name, email, password, phone, gender, dob, department, year_of_study):
    """
    STORED PROCEDURE: sp_register_student
    ──────────────────────────────────────
    Validates input, hashes password, inserts student row,
    fires post-insert notification trigger, logs audit.
    Returns (True, student_id) or (False, error_message).
    """
    conn = DB()
    try:
        # Validation block (PL logic)
        if not full_name or not email or not password:
            return False, "Name, email and password are required."
        if len(password) < 6:
            return False, "Password must be at least 6 characters."

        # Check uniqueness (SELECT before INSERT — PL guard)
        existing = conn.execute(
            "SELECT student_id FROM student WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            return False, "An account with this email already exists."

        pw_hash = _hash(password)

        # Core INSERT
        cur = conn.execute("""
            INSERT INTO student (full_name, email, phone, password_hash, gender, dob, department, year_of_study)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (full_name, email, phone or None, pw_hash,
              gender or None, dob or None, department or None, year_of_study or None))

        student_id = cur.lastrowid

        # TRIGGER SIMULATION: fire welcome notification
        _trigger_welcome_notification(conn, 'student', student_id, full_name)

        # AUDIT LOG
        _audit(conn, 'REGISTER', 'student', student_id, email, f'New student registered: {full_name}')

        conn.commit()
        return True, student_id

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sp_login(email, password, role):
    """
    STORED PROCEDURE: sp_login
    ───────────────────────────
    Authenticates a student or counsellor.
    Returns (True, user_dict) or (False, error_message).
    Role must be 'student' or 'counsellor'.
    """
    conn = DB()
    try:
        pw_hash = _hash(password)

        if role == 'student':
            row = conn.execute("""
                SELECT student_id AS id, full_name, email, department, year_of_study, gender
                FROM   student
                WHERE  email = ? AND password_hash = ? AND is_active = 1
            """, (email, pw_hash)).fetchone()
        else:
            row = conn.execute("""
                SELECT counsellor_id AS id, full_name, email, specialization, experience_years
                FROM   counsellor
                WHERE  email = ? AND password_hash = ? AND available = 1
            """, (email, pw_hash)).fetchone()

        if not row:
            return False, "Invalid email or password."

        _audit(conn, 'LOGIN', role, row['id'], email, f'{role} logged in')
        conn.commit()
        return True, dict(row)

    finally:
        conn.close()


def sp_book_appointment(student_id, counsellor_id, apt_date, apt_time, mode, reason):
    """
    STORED PROCEDURE: sp_book_appointment
    ──────────────────────────────────────
    Books an appointment with full validation:
      1. Checks counsellor availability
      2. Checks for double-booking (same slot)
      3. Checks student doesn't already have a booked slot with same counsellor same day
      4. Inserts appointment
      5. Fires notification triggers for both parties
      6. Writes audit log
    """
    conn = DB()
    try:
        # Guard 1: counsellor exists and is available
        c = conn.execute("""
            SELECT counsellor_id, full_name, max_students FROM counsellor
            WHERE counsellor_id = ? AND available = 1
        """, (counsellor_id,)).fetchone()
        if not c:
            return False, "Counsellor is not available."

        # Guard 2: slot already taken by another student
        clash = conn.execute("""
            SELECT appointment_id FROM appointment
            WHERE counsellor_id = ? AND apt_date = ? AND apt_time = ?
              AND status = 'booked'
        """, (counsellor_id, apt_date, apt_time)).fetchone()
        if clash:
            return False, "That time slot is already booked. Please choose another time."

        # Guard 3: student already has appointment with this counsellor today
        dup = conn.execute("""
            SELECT appointment_id FROM appointment
            WHERE student_id = ? AND counsellor_id = ? AND apt_date = ? AND status = 'booked'
        """, (student_id, counsellor_id, apt_date)).fetchone()
        if dup:
            return False, "You already have an appointment with this counsellor on that day."

        # Core INSERT
        cur = conn.execute("""
            INSERT INTO appointment (student_id, counsellor_id, apt_date, apt_time, mode, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student_id, counsellor_id, apt_date, apt_time, mode, reason or ''))

        apt_id = cur.lastrowid

        # TRIGGER: notify student
        _trigger_notify(conn, 'student', student_id,
            f"✅ Appointment booked with {c['full_name']} on {apt_date} at {apt_time}.")

        # TRIGGER: notify counsellor
        s = conn.execute("SELECT full_name FROM student WHERE student_id=?", (student_id,)).fetchone()
        _trigger_notify(conn, 'counsellor', counsellor_id,
            f"📅 New booking from {s['full_name']} on {apt_date} at {apt_time}.")

        _audit(conn, 'BOOK', 'appointment', apt_id,
               f'student:{student_id}', f'Booked with counsellor:{counsellor_id} on {apt_date}')

        conn.commit()
        return True, apt_id

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sp_cancel_appointment(appointment_id, cancelled_by, role):
    """
    STORED PROCEDURE: sp_cancel_appointment
    ─────────────────────────────────────────
    Cancels an appointment if it's still in 'booked' state.
    Notifies the other party.
    """
    conn = DB()
    try:
        apt = conn.execute("""
            SELECT a.*, s.full_name AS sname, c.full_name AS cname,
                   s.student_id, c.counsellor_id
            FROM   appointment a
            JOIN   student    s ON s.student_id    = a.student_id
            JOIN   counsellor c ON c.counsellor_id = a.counsellor_id
            WHERE  a.appointment_id = ?
        """, (appointment_id,)).fetchone()

        if not apt:
            return False, "Appointment not found."
        if apt['status'] != 'booked':
            return False, "Only booked appointments can be cancelled."

        conn.execute("""
            UPDATE appointment SET status = 'cancelled' WHERE appointment_id = ?
        """, (appointment_id,))

        # TRIGGER: cross-notify
        if role == 'student':
            _trigger_notify(conn, 'counsellor', apt['counsellor_id'],
                f"❌ {apt['sname']} cancelled their appointment on {apt['apt_date']}.")
        else:
            _trigger_notify(conn, 'student', apt['student_id'],
                f"❌ Your appointment with {apt['cname']} on {apt['apt_date']} was cancelled.")

        _audit(conn, 'CANCEL', 'appointment', appointment_id,
               f'{role}:{cancelled_by}', f'Cancelled apt on {apt["apt_date"]}')

        conn.commit()
        return True, "Appointment cancelled."

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sp_complete_session(appointment_id, notes, duration, diagnosis_category_id,
                        severity, follow_up_needed, counsellor_id):
    """
    STORED PROCEDURE: sp_complete_session
    ──────────────────────────────────────
    Marks appointment as completed and creates the session record.
    Also fires the recommendation engine for the student.
    This is the most complex PL unit in the system.
    """
    conn = DB()
    try:
        # Verify ownership
        apt = conn.execute("""
            SELECT * FROM appointment
            WHERE appointment_id = ? AND counsellor_id = ? AND status = 'booked'
        """, (appointment_id, counsellor_id)).fetchone()

        if not apt:
            return False, "Appointment not found or already processed."

        today = date.today().isoformat()

        # INSERT session record
        conn.execute("""
            INSERT INTO session
                (appointment_id, session_date, duration_min, notes,
                 diagnosis_category, severity, follow_up_needed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (appointment_id, today, duration, notes,
              diagnosis_category_id or None, severity or None, int(follow_up_needed)))

        # UPDATE appointment status
        conn.execute("""
            UPDATE appointment SET status = 'completed' WHERE appointment_id = ?
        """, (appointment_id,))

        # TRIGGER: personalised recommendation notification for student
        if diagnosis_category_id:
            cat = conn.execute(
                "SELECT name FROM diagnosis_category WHERE category_id=?",
                (diagnosis_category_id,)
            ).fetchone()
            if cat:
                _trigger_notify(conn, 'student', apt['student_id'],
                    f"💡 New personalised recommendations available for: {cat['name']}. "
                    f"Check your dashboard!")

        # TRIGGER: schedule follow-up reminder if needed
        if follow_up_needed:
            fu_date = (date.today() + timedelta(days=7)).isoformat()
            _trigger_notify(conn, 'student', apt['student_id'],
                f"🔔 Your counsellor recommends a follow-up session around {fu_date}.")
            _trigger_notify(conn, 'counsellor', counsellor_id,
                f"🔔 Follow-up reminder set for student (apt #{appointment_id}).")

        _audit(conn, 'COMPLETE', 'session', appointment_id,
               f'counsellor:{counsellor_id}',
               f'Session completed. Diagnosis: {diagnosis_category_id}, Severity: {severity}')

        conn.commit()
        return True, "Session completed."

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sp_submit_feedback(appointment_id, student_id, feedback, rating):
    """
    STORED PROCEDURE: sp_submit_feedback
    ──────────────────────────────────────
    Student submits post-session feedback and rating.
    Can only be done once per session.
    """
    conn = DB()
    try:
        # Verify session belongs to student and is completed
        row = conn.execute("""
            SELECT s.session_id, s.student_feedback FROM session s
            JOIN   appointment a ON a.appointment_id = s.appointment_id
            WHERE  s.appointment_id = ? AND a.student_id = ?
        """, (appointment_id, student_id)).fetchone()

        if not row:
            return False, "Session not found."
        if row['student_feedback']:
            return False, "Feedback already submitted."
        if not (1 <= int(rating) <= 5):
            return False, "Rating must be between 1 and 5."

        conn.execute("""
            UPDATE session SET student_feedback = ?, student_rating = ?
            WHERE  session_id = ?
        """, (feedback, int(rating), row['session_id']))

        _audit(conn, 'FEEDBACK', 'session', row['session_id'],
               f'student:{student_id}', f'Rating: {rating}')
        conn.commit()
        return True, "Feedback submitted. Thank you!"

    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def sp_mark_notifications_read(user_type, user_id):
    """STORED PROCEDURE: Mark all unread notifications as read."""
    conn = DB()
    try:
        conn.execute("""
            UPDATE notification SET is_read = 1
            WHERE user_type = ? AND user_id = ? AND is_read = 0
        """, (user_type, user_id))
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — TRIGGER FUNCTIONS (PL)
# These simulate database-level AFTER INSERT / AFTER UPDATE triggers.
# They fire automatically inside stored procedures.
# ══════════════════════════════════════════════════════════════════════════════

def _trigger_welcome_notification(conn, user_type, user_id, name):
    """
    TRIGGER: trg_after_student_insert
    Fires after a new student registers.
    Inserts a welcome notification.
    """
    conn.execute("""
        INSERT INTO notification (user_type, user_id, message)
        VALUES (?, ?, ?)
    """, (user_type, user_id,
          f"🌿 Welcome to MindBridge, {name}! Browse our counsellors and book your first session."))


def _trigger_notify(conn, user_type, user_id, message):
    """
    TRIGGER: trg_insert_notification
    Generic notification trigger. Called by other PL procedures.
    """
    conn.execute("""
        INSERT INTO notification (user_type, user_id, message)
        VALUES (?, ?, ?)
    """, (user_type, user_id, message))


def _audit(conn, action, entity, entity_id, actor, detail):
    """
    TRIGGER: trg_audit_log
    Every write operation calls this to maintain a tamper-evident audit trail.
    """
    conn.execute("""
        INSERT INTO audit_log (action, entity, entity_id, actor, detail)
        VALUES (?, ?, ?, ?, ?)
    """, (action, entity, entity_id, actor, detail))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — VIEW QUERIES (SQL VIEWs as named Python functions)
# Each function encodes a complex SELECT that would be a CREATE VIEW in Oracle.
# ══════════════════════════════════════════════════════════════════════════════

def view_student_dashboard(student_id):
    """
    VIEW: v_student_dashboard
    Returns all data needed to render the student's main page:
    appointments, stats, and unread notification count.
    """
    conn = DB()
    try:
        # Upcoming appointments with counsellor info
        upcoming = conn.execute("""
            SELECT  a.appointment_id, a.apt_date, a.apt_time, a.mode, a.status, a.reason,
                    c.full_name AS counsellor_name, c.specialization
            FROM    appointment a
            JOIN    counsellor  c ON c.counsellor_id = a.counsellor_id
            WHERE   a.student_id = ? AND a.status = 'booked'
                    AND a.apt_date >= date('now')
            ORDER   BY a.apt_date ASC, a.apt_time ASC
        """, (student_id,)).fetchall()

        # Completed sessions with diagnosis info
        history = conn.execute("""
            SELECT  a.appointment_id, a.apt_date, a.mode,
                    c.full_name AS counsellor_name,
                    s.duration_min, s.severity, s.student_rating,
                    s.student_feedback, s.follow_up_needed,
                    d.name AS diagnosis_name
            FROM    appointment a
            JOIN    counsellor       c ON c.counsellor_id  = a.counsellor_id
            JOIN    session          s ON s.appointment_id = a.appointment_id
            LEFT JOIN diagnosis_category d ON d.category_id = s.diagnosis_category
            WHERE   a.student_id = ?
            ORDER   BY a.apt_date DESC
        """, (student_id,)).fetchall()

        # Aggregate stats (computed in SQL)
        stats = conn.execute("""
            SELECT
                COUNT(CASE WHEN a.status='completed' THEN 1 END)  AS total_sessions,
                COUNT(CASE WHEN a.status='booked'    THEN 1 END)  AS upcoming_count,
                COUNT(CASE WHEN a.status='cancelled' THEN 1 END)  AS cancelled_count,
                COALESCE(SUM(CASE WHEN a.status='completed' THEN s.duration_min END), 0) AS total_minutes,
                COALESCE(AVG(CASE WHEN s.student_rating IS NOT NULL THEN s.student_rating END), 0) AS avg_rating_given
            FROM  appointment a
            LEFT JOIN session s ON s.appointment_id = a.appointment_id
            WHERE a.student_id = ?
        """, (student_id,)).fetchone()

        # Unread notifications
        notifs = conn.execute("""
            SELECT message, created_at, is_read
            FROM   notification
            WHERE  user_type='student' AND user_id=?
            ORDER  BY created_at DESC LIMIT 10
        """, (student_id,)).fetchall()

        unread_count = conn.execute("""
            SELECT COUNT(*) AS n FROM notification
            WHERE user_type='student' AND user_id=? AND is_read=0
        """, (student_id,)).fetchone()['n']

        return {
            'upcoming':     [dict(r) for r in upcoming],
            'history':      [dict(r) for r in history],
            'stats':        dict(stats),
            'notifications': [dict(r) for r in notifs],
            'unread_count': unread_count,
        }
    finally:
        conn.close()


def view_counsellor_dashboard(counsellor_id):
    """
    VIEW: v_counsellor_dashboard
    Returns all sessions, upcoming bookings, and performance stats
    for a counsellor's dashboard.
    """
    conn = DB()
    try:
        today = date.today().isoformat()

        today_apts = conn.execute("""
            SELECT  a.appointment_id, a.apt_time, a.mode, a.reason,
                    s.full_name AS student_name, s.department, s.year_of_study
            FROM    appointment a
            JOIN    student s ON s.student_id = a.student_id
            WHERE   a.counsellor_id = ? AND a.apt_date = ? AND a.status = 'booked'
            ORDER   BY a.apt_time
        """, (counsellor_id, today)).fetchall()

        upcoming = conn.execute("""
            SELECT  a.appointment_id, a.apt_date, a.apt_time, a.mode, a.reason,
                    s.full_name AS student_name, s.department, s.year_of_study
            FROM    appointment a
            JOIN    student s ON s.student_id = a.student_id
            WHERE   a.counsellor_id = ? AND a.apt_date > ? AND a.status = 'booked'
            ORDER   BY a.apt_date, a.apt_time
        """, (counsellor_id, today)).fetchall()

        all_sessions = conn.execute("""
            SELECT  a.appointment_id, a.apt_date, a.status,
                    s.full_name AS student_name,
                    se.duration_min, se.severity, se.student_rating,
                    d.name AS diagnosis_name, se.follow_up_needed
            FROM    appointment a
            JOIN    student          s  ON s.student_id    = a.student_id
            LEFT JOIN session        se ON se.appointment_id = a.appointment_id
            LEFT JOIN diagnosis_category d ON d.category_id = se.diagnosis_category
            WHERE   a.counsellor_id = ?
            ORDER   BY a.apt_date DESC
        """, (counsellor_id,)).fetchall()

        stats = conn.execute("""
            SELECT
                COUNT(CASE WHEN a.status='completed' THEN 1 END) AS completed,
                COUNT(CASE WHEN a.status='booked'    THEN 1 END) AS upcoming,
                COUNT(CASE WHEN a.status='cancelled' THEN 1 END) AS cancelled,
                ROUND(AVG(CASE WHEN se.student_rating IS NOT NULL
                               THEN se.student_rating END), 1)   AS avg_rating,
                COUNT(CASE WHEN se.follow_up_needed=1 THEN 1 END) AS follow_ups_needed
            FROM  appointment a
            LEFT JOIN session se ON se.appointment_id = a.appointment_id
            WHERE a.counsellor_id = ?
        """, (counsellor_id,)).fetchone()

        # Breakdown of diagnoses handled — useful for counsellor insight
        diagnosis_breakdown = conn.execute("""
            SELECT  d.name, COUNT(*) AS count
            FROM    session          se
            JOIN    appointment       a  ON a.appointment_id  = se.appointment_id
            JOIN    diagnosis_category d ON d.category_id     = se.diagnosis_category
            WHERE   a.counsellor_id = ?
            GROUP   BY d.name
            ORDER   BY count DESC
        """, (counsellor_id,)).fetchall()

        notifs = conn.execute("""
            SELECT message, created_at, is_read
            FROM   notification
            WHERE  user_type='counsellor' AND user_id=?
            ORDER  BY created_at DESC LIMIT 10
        """, (counsellor_id,)).fetchall()

        unread_count = conn.execute("""
            SELECT COUNT(*) AS n FROM notification
            WHERE user_type='counsellor' AND user_id=? AND is_read=0
        """, (counsellor_id,)).fetchone()['n']

        return {
            'today_apts':        [dict(r) for r in today_apts],
            'upcoming':          [dict(r) for r in upcoming],
            'all_sessions':      [dict(r) for r in all_sessions],
            'stats':             dict(stats),
            'diagnosis_breakdown': [dict(r) for r in diagnosis_breakdown],
            'notifications':     [dict(r) for r in notifs],
            'unread_count':      unread_count,
        }
    finally:
        conn.close()


def view_recommendations_for_student(student_id):
    """
    VIEW: v_student_recommendations
    ─────────────────────────────────
    THE RECOMMENDATION ENGINE — pure SQL.

    How it works:
      1. Finds all diagnosis categories assigned to this student across sessions.
      2. Joins the recommendation table to fetch matching resources.
      3. Ranks by priority (1=high first) and recency of diagnosis.
      4. Deduplicates so the same recommendation doesn't repeat.

    Returns personalised, prioritised recommendations based on
    what the counsellor has actually diagnosed.
    """
    conn = DB()
    try:
        recs = conn.execute("""
            SELECT DISTINCT
                r.rec_id,
                r.title,
                r.body,
                r.resource_link,
                r.priority,
                d.name          AS category_name,
                MAX(a.apt_date) AS most_recent_session
            FROM   recommendation        r
            JOIN   diagnosis_category    d  ON d.category_id  = r.category_id
            JOIN   session               se ON se.diagnosis_category = r.category_id
            JOIN   appointment           a  ON a.appointment_id = se.appointment_id
            WHERE  a.student_id = ?
               AND a.status     = 'completed'
            GROUP  BY r.rec_id
            ORDER  BY r.priority ASC, most_recent_session DESC
        """, (student_id,)).fetchall()

        # Also get category-level summary (PL: group by category for UI sections)
        categories = conn.execute("""
            SELECT DISTINCT d.name, d.description, d.category_id
            FROM   diagnosis_category  d
            JOIN   session             se ON se.diagnosis_category = d.category_id
            JOIN   appointment         a  ON a.appointment_id = se.appointment_id
            WHERE  a.student_id = ? AND a.status = 'completed'
        """, (student_id,)).fetchall()

        return {
            'recommendations': [dict(r) for r in recs],
            'categories':      [dict(c) for c in categories],
        }
    finally:
        conn.close()


def view_all_counsellors():
    """VIEW: List of available counsellors for booking."""
    conn = DB()
    try:
        rows = conn.execute("""
            SELECT  c.counsellor_id, c.full_name, c.specialization,
                    c.experience_years, c.bio,
                    COUNT(CASE WHEN a.status='completed' THEN 1 END) AS sessions_done,
                    ROUND(AVG(se.student_rating), 1)                 AS avg_rating
            FROM    counsellor   c
            LEFT JOIN appointment a  ON a.counsellor_id  = c.counsellor_id
            LEFT JOIN session     se ON se.appointment_id = a.appointment_id
            WHERE   c.available = 1
            GROUP   BY c.counsellor_id
            ORDER   BY c.experience_years DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def view_appointment_detail(appointment_id):
    """VIEW: Full detail for one appointment including session if it exists."""
    conn = DB()
    try:
        apt = conn.execute("""
            SELECT  a.*,
                    s.full_name  AS student_name,  s.department,
                    c.full_name  AS counsellor_name, c.specialization,
                    se.session_id, se.duration_min, se.notes, se.severity,
                    se.student_feedback, se.student_rating, se.follow_up_needed,
                    d.name AS diagnosis_name
            FROM    appointment  a
            JOIN    student      s  ON s.student_id    = a.student_id
            JOIN    counsellor   c  ON c.counsellor_id = a.counsellor_id
            LEFT JOIN session    se ON se.appointment_id = a.appointment_id
            LEFT JOIN diagnosis_category d ON d.category_id = se.diagnosis_category
            WHERE   a.appointment_id = ?
        """, (appointment_id,)).fetchone()
        return dict(apt) if apt else None
    finally:
        conn.close()


def view_diagnosis_categories():
    """VIEW: All diagnosis categories (for counsellor dropdown)."""
    conn = DB()
    try:
        rows = conn.execute("SELECT * FROM diagnosis_category ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — INITIALISE DATABASE
# Call this once on startup to create tables and seed data.
# ══════════════════════════════════════════════════════════════════════════════

def init_db():
    """
    Runs DDL (schema creation) and DML (seed data) against the SQLite database.
    Safe to call multiple times — uses CREATE IF NOT EXISTS and INSERT OR IGNORE.
    """
    conn = DB()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()

