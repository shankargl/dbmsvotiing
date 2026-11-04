import os
import sqlite3
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-this")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database", "voting.db")


# ---------------- DATABASE CONNECTION ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------- DATABASE INITIALIZATION ----------------

def init_db():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voters (
            voter_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'voter'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS elections (
            election_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            party TEXT NOT NULL,
            election_id INTEGER NOT NULL,
            FOREIGN KEY (election_id)
                REFERENCES elections(election_id)
                ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
            voter_id TEXT NOT NULL,
            candidate_id INTEGER NOT NULL,
            election_id INTEGER NOT NULL,
            vote_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (voter_id)
                REFERENCES voters(voter_id),

            FOREIGN KEY (candidate_id)
                REFERENCES candidates(candidate_id),

            FOREIGN KEY (election_id)
                REFERENCES elections(election_id),

            UNIQUE (voter_id, election_id)
        )
    """)

    # Create default administrator if it does not already exist.
    cursor.execute("""
        INSERT OR IGNORE INTO voters
        (voter_id, name, password, role)
        VALUES (?, ?, ?, ?)
    """, (
        "ADMIN",
        "Administrator",
        generate_password_hash("admin123"),
        "admin"
    ))

    # Create demo voters if they do not already exist.
    demo_voters = [
        ("V001", "Rahul", "123456", "voter"),
        ("V002", "Priya", "123456", "voter"),
        ("V003", "Arjun", "123456", "voter"),
        ("V004", "Sneha", "123456", "voter"),
        ("V005", "Kiran", "123456", "voter")
    ]

    for voter in demo_voters:
        cursor.execute("""
            INSERT OR IGNORE INTO voters
            (voter_id, name, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            voter[0],
            voter[1],
            generate_password_hash(voter[2]),
            voter[3]
        ))

    # Create the sample election only if it does not exist.
    cursor.execute("""
        SELECT election_id
        FROM elections
        WHERE title = ?
    """, ("College Student Council Election 2026",))

    election = cursor.fetchone()

    if election is None:
        cursor.execute("""
            INSERT INTO elections (title, status)
            VALUES (?, ?)
        """, (
            "College Student Council Election 2026",
            "Active"
        ))

        election_id = cursor.lastrowid

        sample_candidates = [
            ("Aarav Sharma", "Unity Party"),
            ("Ananya Rao", "Progress Party"),
            ("Rohan Kumar", "Student First")
        ]

        for candidate in sample_candidates:
            cursor.execute("""
                INSERT INTO candidates
                (name, party, election_id)
                VALUES (?, ?, ?)
            """, (
                candidate[0],
                candidate[1],
                election_id
            ))

    conn.commit()
    conn.close()


# ---------------- AUTHENTICATION DECORATORS ----------------

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "voter_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("home"))

        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Administrator access required.", "error")
            return redirect(url_for("home"))

        return func(*args, **kwargs)

    return wrapper


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    conn = get_db()

    elections = conn.execute("""
        SELECT *
        FROM elections
        ORDER BY election_id DESC
    """).fetchall()

    active_election = conn.execute("""
        SELECT *
        FROM elections
        WHERE status = 'Active'
        ORDER BY election_id DESC
        LIMIT 1
    """).fetchone()

    candidates = []

    if active_election:
        candidates = conn.execute("""
            SELECT *
            FROM candidates
            WHERE election_id = ?
            ORDER BY candidate_id
        """, (active_election["election_id"],)).fetchall()

    already_voted = False

    if session.get("role") == "voter" and active_election:
        vote = conn.execute("""
            SELECT vote_id
            FROM votes
            WHERE voter_id = ?
            AND election_id = ?
        """, (
            session["voter_id"],
            active_election["election_id"]
        )).fetchone()

        already_voted = vote is not None

    conn.close()

    return render_template(
        "index.html",
        elections=elections,
        active_election=active_election,
        candidates=candidates,
        already_voted=already_voted,
        show_admin=False,
        show_results=False
    )


# ---------------- VOTER REGISTRATION ----------------

@app.route("/register", methods=["POST"])
def register():
    voter_id = request.form.get("voter_id", "").strip().upper()
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")

    if not voter_id or not name or not password:
        flash("All fields are required.", "error")
        return redirect(url_for("home"))

    if len(password) < 6:
        flash("Password must contain at least 6 characters.", "error")
        return redirect(url_for("home"))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO voters
            (voter_id, name, password, role)
            VALUES (?, ?, ?, 'voter')
        """, (
            voter_id,
            name,
            generate_password_hash(password)
        ))

        conn.commit()
        flash("Registration successful. Please login.", "success")

    except sqlite3.IntegrityError:
        flash("Voter ID already exists.", "error")

    finally:
        conn.close()

    return redirect(url_for("home"))


# ---------------- LOGIN ----------------

@app.route("/login", methods=["POST"])
def login():
    voter_id = request.form.get("voter_id", "").strip().upper()
    password = request.form.get("password", "")

    conn = get_db()

    voter = conn.execute("""
        SELECT *
        FROM voters
        WHERE voter_id = ?
    """, (voter_id,)).fetchone()

    conn.close()

    if voter and check_password_hash(voter["password"], password):
        session.clear()
        session["voter_id"] = voter["voter_id"]
        session["name"] = voter["name"]
        session["role"] = voter["role"]

        flash("Login successful.", "success")

    else:
        flash("Invalid voter ID or password.", "error")

    return redirect(url_for("home"))


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# ---------------- CAST VOTE ----------------

@app.route("/vote", methods=["POST"])
@login_required
def cast_vote():
    if session.get("role") != "voter":
        flash("Only registered voters can vote.", "error")
        return redirect(url_for("home"))

    candidate_id = request.form.get("candidate_id", type=int)
    election_id = request.form.get("election_id", type=int)

    if not candidate_id or not election_id:
        flash("Please select a candidate.", "error")
        return redirect(url_for("home"))

    conn = get_db()

    election = conn.execute("""
        SELECT *
        FROM elections
        WHERE election_id = ?
        AND status = 'Active'
    """, (election_id,)).fetchone()

    candidate = conn.execute("""
        SELECT *
        FROM candidates
        WHERE candidate_id = ?
        AND election_id = ?
    """, (candidate_id, election_id)).fetchone()

    if not election or not candidate:
        conn.close()
        flash("Invalid election or candidate.", "error")
        return redirect(url_for("home"))

    try:
        conn.execute("""
            INSERT INTO votes
            (voter_id, candidate_id, election_id)
            VALUES (?, ?, ?)
        """, (
            session["voter_id"],
            candidate_id,
            election_id
        ))

        conn.commit()
        flash("Your vote has been recorded successfully.", "success")

    except sqlite3.IntegrityError:
        flash("You have already voted in this election.", "error")

    finally:
        conn.close()

    return redirect(url_for("home"))


# ---------------- RESULTS (ADMIN ONLY) ----------------

@app.route("/results")
@login_required
@admin_required
def results():
    conn = get_db()

    elections = conn.execute("""
        SELECT *
        FROM elections
        ORDER BY election_id DESC
    """).fetchall()

    selected_id = request.args.get("election_id", type=int)

    if not selected_id and elections:
        selected_id = elections[0]["election_id"]

    selected_election = None
    results_data = []
    total_votes = 0

    if selected_id:
        selected_election = conn.execute("""
            SELECT *
            FROM elections
            WHERE election_id = ?
        """, (selected_id,)).fetchone()

        if selected_election:
            results_data = conn.execute("""
                SELECT
                    c.candidate_id,
                    c.name,
                    c.party,
                    COUNT(v.vote_id) AS vote_count
                FROM candidates c
                LEFT JOIN votes v
                    ON c.candidate_id = v.candidate_id
                WHERE c.election_id = ?
                GROUP BY c.candidate_id, c.name, c.party
                ORDER BY vote_count DESC, c.name ASC
            """, (selected_id,)).fetchall()

            total_votes = sum(row["vote_count"] for row in results_data)

    conn.close()

    return render_template(
        "index.html",
        elections=elections,
        active_election=None,
        candidates=[],
        already_voted=False,
        show_admin=False,
        show_results=True,
        selected_election=selected_election,
        results_data=results_data,
        total_votes=total_votes
    )


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@login_required
@admin_required
def admin():
    conn = get_db()

    elections = conn.execute("""
        SELECT *
        FROM elections
        ORDER BY election_id DESC
    """).fetchall()

    voters_count = conn.execute("""
        SELECT COUNT(*) AS total
        FROM voters
        WHERE role = 'voter'
    """).fetchone()["total"]

    votes_count = conn.execute("""
        SELECT COUNT(*) AS total
        FROM votes
    """).fetchone()["total"]

    candidates_count = conn.execute("""
        SELECT COUNT(*) AS total
        FROM candidates
    """).fetchone()["total"]

    all_candidates = conn.execute("""
        SELECT
            c.candidate_id,
            c.name,
            c.party,
            c.election_id,
            e.title AS election_title
        FROM candidates c
        JOIN elections e ON e.election_id = c.election_id
        ORDER BY c.candidate_id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        elections=elections,
        active_election=None,
        candidates=[],
        already_voted=False,
        show_admin=True,
        show_results=False,
        voters_count=voters_count,
        votes_count=votes_count,
        candidates_count=candidates_count,
        all_candidates=all_candidates
    )


# ---------------- ADD ELECTION ----------------

@app.route("/admin/add-election", methods=["POST"])
@login_required
@admin_required
def add_election():
    title = request.form.get("title", "").strip()
    status = request.form.get("status", "Active")

    if not title:
        flash("Election title is required.", "error")
        return redirect(url_for("admin"))

    if status not in ["Active", "Closed"]:
        status = "Closed"

    conn = get_db()

    conn.execute("""
        INSERT INTO elections (title, status)
        VALUES (?, ?)
    """, (title, status))

    conn.commit()
    conn.close()

    flash("Election created successfully.", "success")
    return redirect(url_for("admin"))


# ---------------- ADD CANDIDATE ----------------

@app.route("/admin/add-candidate", methods=["POST"])
@login_required
@admin_required
def add_candidate():
    name = request.form.get("name", "").strip()
    party = request.form.get("party", "").strip()
    election_id = request.form.get("election_id", type=int)

    if not name or not party or not election_id:
        flash("Please fill all candidate details.", "error")
        return redirect(url_for("admin"))

    conn = get_db()

    election = conn.execute("""
        SELECT election_id
        FROM elections
        WHERE election_id = ?
    """, (election_id,)).fetchone()

    if not election:
        conn.close()
        flash("Invalid election.", "error")
        return redirect(url_for("admin"))

    conn.execute("""
        INSERT INTO candidates
        (name, party, election_id)
        VALUES (?, ?, ?)
    """, (name, party, election_id))

    conn.commit()
    conn.close()

    flash("Candidate added successfully.", "success")
    return redirect(url_for("admin"))


# ---------------- UPDATE ELECTION STATUS ----------------

@app.route("/admin/toggle-election/<int:election_id>", methods=["POST"])
@login_required
@admin_required
def toggle_election(election_id):
    conn = get_db()

    election = conn.execute("""
        SELECT *
        FROM elections
        WHERE election_id = ?
    """, (election_id,)).fetchone()

    if election:
        new_status = "Closed" if election["status"] == "Active" else "Active"

        conn.execute("""
            UPDATE elections
            SET status = ?
            WHERE election_id = ?
        """, (new_status, election_id))

        conn.commit()
        flash("Election status updated.", "success")
    else:
        flash("Election not found.", "error")

    conn.close()
    return redirect(url_for("admin"))


# ---------------- DELETE ELECTION ----------------

@app.route("/admin/delete-election/<int:election_id>", methods=["POST"])
@login_required
@admin_required
def delete_election(election_id):
    conn = get_db()

    election = conn.execute("""
        SELECT election_id
        FROM elections
        WHERE election_id = ?
    """, (election_id,)).fetchone()

    if not election:
        conn.close()
        flash("Election not found.", "error")
        return redirect(url_for("admin"))

    try:
        # Remove dependent rows first because the existing votes table
        # does not declare ON DELETE CASCADE for its foreign keys.
        conn.execute("DELETE FROM votes WHERE election_id = ?", (election_id,))
        conn.execute("DELETE FROM candidates WHERE election_id = ?", (election_id,))
        conn.execute("DELETE FROM elections WHERE election_id = ?", (election_id,))
        conn.commit()
        flash("Election, candidates, and related votes deleted successfully.", "success")

    except sqlite3.Error:
        conn.rollback()
        flash("Could not delete the election. Please try again.", "error")

    finally:
        conn.close()

    return redirect(url_for("admin"))


# ---------------- DELETE CANDIDATE / ELECTION MEMBER ----------------

@app.route("/admin/delete-candidate/<int:candidate_id>", methods=["POST"])
@login_required
@admin_required
def delete_candidate(candidate_id):
    conn = get_db()

    candidate = conn.execute("""
        SELECT candidate_id
        FROM candidates
        WHERE candidate_id = ?
    """, (candidate_id,)).fetchone()

    if not candidate:
        conn.close()
        flash("Candidate/member not found.", "error")
        return redirect(url_for("admin"))

    try:
        # Remove votes for this candidate before deleting the candidate.
        conn.execute("DELETE FROM votes WHERE candidate_id = ?", (candidate_id,))
        conn.execute("DELETE FROM candidates WHERE candidate_id = ?", (candidate_id,))
        conn.commit()
        flash("Candidate/member and related votes deleted successfully.", "success")

    except sqlite3.Error:
        conn.rollback()
        flash("Could not delete the candidate/member. Please try again.", "error")

    finally:
        conn.close()

    return redirect(url_for("admin"))


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
