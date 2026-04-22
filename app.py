"""
Quality Compliance Document Program
A Flask web application to track and generate compliance documents
for RoHS, REACH, PFAS, and Montreal Protocol standards.
"""

import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from pdf_generator import generate_compliance_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "compliance.db")
DOCS_DIR = os.path.join(BASE_DIR, "generated_docs")
os.makedirs(DOCS_DIR, exist_ok=True)

app = Flask(__name__, template_folder=".")
app.secret_key = "compliance_app_secret_2026"


@app.context_processor
def inject_now():
    return {"now": datetime.now(), "request": __import__("flask").request}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number TEXT NOT NULL UNIQUE,
            description TEXT,
            customer TEXT,
            material TEXT,
            rohs_status TEXT DEFAULT 'Unknown',
            reach_status TEXT DEFAULT 'Unknown',
            pfas_status TEXT DEFAULT 'Unknown',
            montreal_status TEXT DEFAULT 'Unknown',
            rohs_notes TEXT,
            reach_notes TEXT,
            pfas_notes TEXT,
            montreal_notes TEXT,
            last_updated TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            contact_name TEXT,
            contact_email TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER,
            part_number TEXT,
            doc_type TEXT,
            customer TEXT,
            file_path TEXT,
            generated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    conn = get_db()
    c = conn.cursor()

    total_parts = c.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    total_docs  = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    # Compliance summary counts
    def status_counts(field):
        rows = c.execute(
            f"SELECT {field}, COUNT(*) as cnt FROM parts GROUP BY {field}"
        ).fetchall()
        return {r[field]: r["cnt"] for r in rows}

    rohs_counts     = status_counts("rohs_status")
    reach_counts    = status_counts("reach_status")
    pfas_counts     = status_counts("pfas_status")
    montreal_counts = status_counts("montreal_status")

    recent_docs = c.execute(
        "SELECT * FROM documents ORDER BY generated_at DESC LIMIT 10"
    ).fetchall()

    recent_parts = c.execute(
        "SELECT * FROM parts ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        total_parts=total_parts,
        total_docs=total_docs,
        rohs_counts=rohs_counts,
        reach_counts=reach_counts,
        pfas_counts=pfas_counts,
        montreal_counts=montreal_counts,
        recent_docs=recent_docs,
        recent_parts=recent_parts,
    )


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------

@app.route("/parts")
def parts_list():
    search = request.args.get("search", "").strip()
    rohs   = request.args.get("rohs", "")
    reach  = request.args.get("reach", "")
    pfas   = request.args.get("pfas", "")
    montreal = request.args.get("montreal", "")

    query  = "SELECT * FROM parts WHERE 1=1"
    params = []

    if search:
        query += " AND (part_number LIKE ? OR description LIKE ? OR customer LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if rohs:
        query += " AND rohs_status = ?"
        params.append(rohs)
    if reach:
        query += " AND reach_status = ?"
        params.append(reach)
    if pfas:
        query += " AND pfas_status = ?"
        params.append(pfas)
    if montreal:
        query += " AND montreal_status = ?"
        params.append(montreal)

    query += " ORDER BY part_number"

    conn = get_db()
    parts = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("parts.html", parts=parts, search=search,
                           rohs=rohs, reach=reach, pfas=pfas, montreal=montreal)


@app.route("/parts/add", methods=["GET", "POST"])
def add_part():
    if request.method == "POST":
        pn   = request.form["part_number"].strip().upper()
        desc = request.form.get("description", "").strip()
        cust = request.form.get("customer", "").strip()
        mat  = request.form.get("material", "").strip()

        rohs_status     = request.form.get("rohs_status", "Unknown")
        reach_status    = request.form.get("reach_status", "Unknown")
        pfas_status     = request.form.get("pfas_status", "Unknown")
        montreal_status = request.form.get("montreal_status", "Unknown")

        rohs_notes     = request.form.get("rohs_notes", "").strip()
        reach_notes    = request.form.get("reach_notes", "").strip()
        pfas_notes     = request.form.get("pfas_notes", "").strip()
        montreal_notes = request.form.get("montreal_notes", "").strip()

        now = datetime.now().strftime("%Y-%m-%d")

        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO parts (part_number, description, customer, material,
                   rohs_status, reach_status, pfas_status, montreal_status,
                   rohs_notes, reach_notes, pfas_notes, montreal_notes, last_updated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pn, desc, cust, mat,
                 rohs_status, reach_status, pfas_status, montreal_status,
                 rohs_notes, reach_notes, pfas_notes, montreal_notes, now)
            )
            conn.commit()
            flash(f"Part {pn} added successfully.", "success")
            return redirect(url_for("parts_list"))
        except sqlite3.IntegrityError:
            flash(f"Part number {pn} already exists.", "danger")
        finally:
            conn.close()

    return render_template("add_part.html", part=None)


@app.route("/parts/<int:part_id>")
def part_detail(part_id):
    conn = get_db()
    part = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    docs = conn.execute(
        "SELECT * FROM documents WHERE part_id = ? ORDER BY generated_at DESC",
        (part_id,)
    ).fetchall()
    conn.close()
    if not part:
        flash("Part not found.", "danger")
        return redirect(url_for("parts_list"))
    return render_template("part_detail.html", part=part, docs=docs)


@app.route("/parts/<int:part_id>/edit", methods=["GET", "POST"])
def edit_part(part_id):
    conn = get_db()
    part = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    if not part:
        flash("Part not found.", "danger")
        conn.close()
        return redirect(url_for("parts_list"))

    if request.method == "POST":
        desc = request.form.get("description", "").strip()
        cust = request.form.get("customer", "").strip()
        mat  = request.form.get("material", "").strip()

        rohs_status     = request.form.get("rohs_status", "Unknown")
        reach_status    = request.form.get("reach_status", "Unknown")
        pfas_status     = request.form.get("pfas_status", "Unknown")
        montreal_status = request.form.get("montreal_status", "Unknown")

        rohs_notes     = request.form.get("rohs_notes", "").strip()
        reach_notes    = request.form.get("reach_notes", "").strip()
        pfas_notes     = request.form.get("pfas_notes", "").strip()
        montreal_notes = request.form.get("montreal_notes", "").strip()

        now = datetime.now().strftime("%Y-%m-%d")

        conn.execute(
            """UPDATE parts SET description=?, customer=?, material=?,
               rohs_status=?, reach_status=?, pfas_status=?, montreal_status=?,
               rohs_notes=?, reach_notes=?, pfas_notes=?, montreal_notes=?,
               last_updated=?
               WHERE id=?""",
            (desc, cust, mat,
             rohs_status, reach_status, pfas_status, montreal_status,
             rohs_notes, reach_notes, pfas_notes, montreal_notes,
             now, part_id)
        )
        conn.commit()
        conn.close()
        flash("Part updated successfully.", "success")
        return redirect(url_for("part_detail", part_id=part_id))

    conn.close()
    return render_template("add_part.html", part=part)


@app.route("/parts/<int:part_id>/delete", methods=["POST"])
def delete_part(part_id):
    conn = get_db()
    conn.execute("DELETE FROM parts WHERE id = ?", (part_id,))
    conn.execute("DELETE FROM documents WHERE part_id = ?", (part_id,))
    conn.commit()
    conn.close()
    flash("Part deleted.", "info")
    return redirect(url_for("parts_list"))


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

STATUSES = {
    "rohs_status":     ["Compliant", "Non-Compliant", "Exempt", "Unknown"],
    "reach_status":    ["Compliant", "Contains SVHC", "Unknown"],
    "pfas_status":     ["PFAS-Free", "Contains PFAS", "Unknown"],
    "montreal_status": ["Compliant", "Contains ODS", "Unknown"],
}

DOC_TYPES = ["RoHS", "REACH", "PFAS", "Montreal Protocol", "Combined (All Standards)"]


@app.route("/documents/generate", methods=["GET", "POST"])
def generate_document():
    conn = get_db()
    parts = conn.execute("SELECT * FROM parts ORDER BY part_number").fetchall()

    if request.method == "POST":
        part_id  = request.form.get("part_id")
        doc_type = request.form.get("doc_type")
        customer = request.form.get("customer", "").strip()
        signatory = request.form.get("signatory", "").strip()
        company   = request.form.get("company", "Schlegel Electronic Materials").strip()

        part = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
        if not part:
            flash("Please select a valid part.", "danger")
            conn.close()
            return render_template("generate_document.html", parts=parts, doc_types=DOC_TYPES)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_pn   = part["part_number"].replace("/", "-")
        safe_type = doc_type.replace(" ", "_").replace("(", "").replace(")", "")
        filename  = f"{safe_pn}_{safe_type}_{timestamp}.pdf"
        file_path = os.path.join(DOCS_DIR, filename)

        generate_compliance_pdf(
            part=dict(part),
            doc_type=doc_type,
            customer=customer,
            signatory=signatory,
            company=company,
            output_path=file_path,
        )

        conn.execute(
            """INSERT INTO documents (part_id, part_number, doc_type, customer, file_path)
               VALUES (?,?,?,?,?)""",
            (part["id"], part["part_number"], doc_type, customer, file_path)
        )
        conn.commit()
        conn.close()

        flash(f"{doc_type} document generated for {part['part_number']}.", "success")
        return redirect(url_for("documents_list"))

    conn.close()
    return render_template("generate_document.html", parts=parts, doc_types=DOC_TYPES)


@app.route("/documents")
def documents_list():
    conn = get_db()
    docs = conn.execute(
        "SELECT * FROM documents ORDER BY generated_at DESC"
    ).fetchall()
    conn.close()
    return render_template("documents.html", docs=docs)


@app.route("/documents/<int:doc_id>/download")
def download_document(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not doc or not os.path.exists(doc["file_path"]):
        flash("Document file not found.", "danger")
        return redirect(url_for("documents_list"))
    return send_file(doc["file_path"], as_attachment=True,
                     download_name=os.path.basename(doc["file_path"]))


@app.route("/documents/<int:doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if doc and os.path.exists(doc["file_path"]):
        os.remove(doc["file_path"])
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    flash("Document deleted.", "info")
    return redirect(url_for("documents_list"))


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@app.route("/customers")
def customers_list():
    conn = get_db()
    customers = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    conn.close()
    return render_template("customers.html", customers=customers)


@app.route("/customers/add", methods=["GET", "POST"])
def add_customer():
    if request.method == "POST":
        name  = request.form["name"].strip()
        cname = request.form.get("contact_name", "").strip()
        email = request.form.get("contact_email", "").strip()
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO customers (name, contact_name, contact_email) VALUES (?,?,?)",
                (name, cname, email)
            )
            conn.commit()
            flash(f"Customer {name} added.", "success")
        except sqlite3.IntegrityError:
            flash(f"Customer {name} already exists.", "danger")
        finally:
            conn.close()
        return redirect(url_for("customers_list"))
    return render_template("add_customer.html")


@app.route("/customers/<int:cust_id>/delete", methods=["POST"])
def delete_customer(cust_id):
    conn = get_db()
    conn.execute("DELETE FROM customers WHERE id = ?", (cust_id,))
    conn.commit()
    conn.close()
    flash("Customer deleted.", "info")
    return redirect(url_for("customers_list"))


# ---------------------------------------------------------------------------
# API: part info for JS (auto-fill generate form)
# ---------------------------------------------------------------------------

@app.route("/api/part/<int:part_id>")
def api_part(part_id):
    conn = get_db()
    part = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    conn.close()
    if not part:
        return jsonify({}), 404
    return jsonify(dict(part))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("\n" + "="*60)
    print("  Quality Compliance Document Program")
    print("  Running at: http://127.0.0.1:5000")
    print("="*60 + "\n")
    app.run(debug=True, port=5000)