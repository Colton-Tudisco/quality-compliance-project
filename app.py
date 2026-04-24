"""
Comply — Compliance Document Management System
{{ settings.get('company_name', '') }}
"""

import os
import sqlite3
import csv
import io
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, send_file, jsonify)
from pdf_generator import generate_compliance_pdf
from fmd_parser import parse_fmd_pdf
from compliance_engine import determine_compliance

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "comply.db")
DOCS_DIR  = os.path.join(BASE_DIR, "generated_docs")
os.makedirs(DOCS_DIR, exist_ok=True)
FMD_DIR = os.path.join(BASE_DIR, "fmd_uploads")
os.makedirs(FMD_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates")
app.secret_key = "comply_secret_2026"

TRADED_VENDORS = [
    "Schlegel Electronic Materials Asia Limited (I/CO-S",
    "Schlegel (Dongguan) Electronics Limited (I/CO-SEMA",
]

# Compliance-relevant keyword flags per material series
HIGH_RISK_SERIES = {"23RCH", "23RA", "23RFIN", "23RSI"}   # Chem, Adhesive, Finish, Silicone
MED_RISK_SERIES  = {"23RR", "23RL", "23RFIB", "23RM"}     # Resin, Liner, Fiber, Metal
LOW_RISK_SERIES  = {"23RY", "23RP", "23RB", "23RWIR"}     # Yarn, Packaging, Bracket, Wire

PFAS_KEYWORDS    = ["teflon", "ptfe", "pfas", "fluorocarbon", "fluoro", "fep", "pvdf",
                    "hfp", "perfluoro", "polyfluoro"]
SVHC_KEYWORDS    = ["latex", "rhoplex", "chromium", "lead", "cadmium", "phthalate",
                    "flame retard", "fr black", "antimony"]
ODS_KEYWORDS     = ["hcfc", "cfc", "halon", "methyl bromide", "freon"]
ROHS_KEYWORDS    = ["lead", "mercury", "cadmium", "chromium vi", "pbde", "pbb",
                    "phthalate", "dehp", "dbp", "bbp", "dibp"]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number     TEXT NOT NULL UNIQUE,
            description     TEXT,
            part_class      TEXT,
            part_type       TEXT,
            product_group   TEXT,
            uom             TEXT,
            commodity_code  TEXT,
            is_traded       INTEGER DEFAULT 0,
            traded_vendor   TEXT,
            is_active       INTEGER DEFAULT 1,
            has_bom         INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now')),
            is_hidden       INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS materials (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number     TEXT NOT NULL UNIQUE,
            description     TEXT,
            material_series TEXT,
            series_desc     TEXT,
            uom             TEXT,
            primary_supplier TEXT,
            supplier_id     TEXT,
            risk_level      TEXT DEFAULT 'Unknown',
            pfas_flag       INTEGER DEFAULT 0,
            svhc_flag       INTEGER DEFAULT 0,
            ods_flag        INTEGER DEFAULT 0,
            rohs_flag       INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bom_lines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_part     TEXT NOT NULL,
            material_part   TEXT NOT NULL,
            level           INTEGER DEFAULT 0,
            qty_per_parent  REAL DEFAULT 0,
            uom             TEXT,
            sort_order      INTEGER DEFAULT 0,
            UNIQUE(parent_part, material_part, level)
        );

        CREATE TABLE IF NOT EXISTS compliance_status (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number     TEXT NOT NULL,
            standard        TEXT NOT NULL,
            status          TEXT DEFAULT 'Unknown',
            notes           TEXT,
            doc_required    INTEGER DEFAULT 0,
            doc_suggested   INTEGER DEFAULT 0,
            last_assessed   TEXT,
            UNIQUE(part_number, standard)
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id     TEXT UNIQUE,
            name            TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS documents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type        TEXT,
            customer        TEXT,
            signatory       TEXT,
            company         TEXT,
            file_path       TEXT,
            generated_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS document_parts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            part_number TEXT,
            status      TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        );

        CREATE TABLE IF NOT EXISTS import_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            import_type TEXT,
            filename    TEXT,
            rows_added  INTEGER DEFAULT 0,
            rows_updated INTEGER DEFAULT 0,
            rows_skipped INTEGER DEFAULT 0,
            imported_at TEXT DEFAULT (datetime('now')),
            notes       TEXT
        );
        
        CREATE TABLE IF NOT EXISTS fmd_files (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number  TEXT NOT NULL UNIQUE,
            filename     TEXT NOT NULL,
            file_path    TEXT NOT NULL,
            uploaded_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS fmd_substances (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            part_number          TEXT NOT NULL,
            material_name        TEXT,
            substance_name       TEXT,
            cas_number           TEXT,
            substance_weight     REAL,
            substance_weight_uom TEXT,
            weight_on_hm_pct     REAL,
            weight_on_total_pct  REAL,
            hm_on_total_pct      REAL,
            parsed_at            TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(part_number) REFERENCES fmd_files(part_number)
        );
                    
        CREATE TABLE IF NOT EXISTS settings(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT NOT NULL UNIQUE,
            value       TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        );
                    
        CREATE TABLE IF NOT EXISTS reference_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category    TEXT NOT NULL,
            value       TEXT NOT NULL,
            sort_order  INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(category, value)
        );
    """)
    conn.commit()
    # Seed default reference data if not already present
    defaults = [
        ("part_class",    "Finished Goods"),
        ("part_class",    "Raw Material"),
        ("part_class",    "Sub-Assembly"),
        ("part_type",     "Manufactured"),
        ("part_type",     "Purchased"),
        ("traded_vendor", "Schlegel Electronic Materials Asia Limited (I/CO-S"),
        ("traded_vendor", "Schlegel (Dongguan) Electronics Limited (I/CO-SEMA"),
        ("product_group", "2301EMI FOF Gasket"),
    ]
    for category, value in defaults:
        c.execute("""
            INSERT OR IGNORE INTO reference_data (category, value)
            VALUES (?, ?)
        """, (category, value))

    # Seed default settings if not already present
    default_settings = [
        ("company_name",      "Default Company Name"),
        ("company_address",   ""),
        ("company_phone",     ""),
        ("company_email",     ""),
        ("company_logo",      ""),
        ("theme",             "navy"),
        ("default_signatory", ""),
    ]
    for key, value in default_settings:
        c.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES (?, ?)
        """, (key, value))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Compliance assessment logic
# ---------------------------------------------------------------------------

def assess_material_flags(description, series):
    """Return dict of compliance flags based on description keywords."""
    desc_lower = (description or "").lower()
    flags = {
        "pfas_flag": int(any(k in desc_lower for k in PFAS_KEYWORDS)),
        "svhc_flag": int(any(k in desc_lower for k in SVHC_KEYWORDS)),
        "ods_flag":  int(any(k in desc_lower for k in ODS_KEYWORDS)),
        "rohs_flag": int(any(k in desc_lower for k in ROHS_KEYWORDS)),
    }
    # Risk level
    if series in HIGH_RISK_SERIES or any(flags.values()):
        risk = "High"
    elif series in MED_RISK_SERIES:
        risk = "Medium"
    elif series in LOW_RISK_SERIES:
        risk = "Low"
    else:
        risk = "Unknown"
    flags["risk_level"] = risk
    return flags


def assess_part_compliance(part_number, conn):
    """
    Roll up BOM material flags to determine per-part compliance
    status for each standard. Returns dict of {standard: status}.
    """
    # Get all materials in this part's BOM (all levels)
    mats = conn.execute("""
        SELECT m.* FROM bom_lines b
        JOIN materials m ON m.part_number = b.material_part
        WHERE b.parent_part = ?
    """, (part_number,)).fetchall()

    standards = {
        "RoHS":             "Compliant",
        "REACH":            "Compliant",
        "PFAS":             "PFAS-Free",
        "Montreal Protocol":"Compliant",
    }
    reasons = {s: [] for s in standards}

    for m in mats:
        if m["rohs_flag"]:
            standards["RoHS"] = "Needs Review"
            reasons["RoHS"].append(m["part_number"])
        if m["svhc_flag"]:
            standards["REACH"] = "Needs Review"
            reasons["REACH"].append(m["part_number"])
        if m["pfas_flag"]:
            standards["PFAS"] = "Contains PFAS"
            reasons["PFAS"].append(m["part_number"])
        if m["ods_flag"]:
            standards["Montreal Protocol"] = "Needs Review"
            reasons["Montreal Protocol"].append(m["part_number"])

    return standards, reasons


def get_compliance_gaps(part_number, conn):
    """Return list of {standard, required, suggested, reason} gaps."""
    statuses = conn.execute(
        "SELECT * FROM compliance_status WHERE part_number = ?",
        (part_number,)
    ).fetchall()
    status_map = {r["standard"]: r for r in statuses}

    gaps = []
    standards = ["RoHS", "REACH", "PFAS", "Montreal Protocol"]
    for std in standards:
        s = status_map.get(std)
        if not s or s["status"] in ("Unknown", "Needs Review"):
            gaps.append({
                "standard": std,
                "required": True,
                "suggested": False,
                "reason": "Status unconfirmed — material review needed"
            })
        elif s["status"] in ("Contains PFAS", "Contains SVHC", "Contains ODS"):
            gaps.append({
                "standard": std,
                "required": True,
                "suggested": False,
                "reason": f"Non-compliant material detected — declaration required"
            })
    # Suggested: third-party test report if any high-risk materials
    has_high = conn.execute("""
        SELECT COUNT(*) FROM bom_lines b
        JOIN materials m ON m.part_number = b.material_part
        WHERE b.parent_part = ? AND m.risk_level = 'High'
    """, (part_number,)).fetchone()[0]
    if has_high:
        gaps.append({
            "standard": "General",
            "required": False,
            "suggested": True,
            "reason": "High-risk materials present — third-party test report recommended"
        })
    return gaps


# ---------------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    import flask
    conn = get_db()

    # Load all settings into a dict keyed by setting name
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in rows}

    # Load theme — default to navy if not set
    theme = settings.get("theme", "navy")

    conn.close()
    return {
        "now":      datetime.now(),
        "request":  flask.request,
        "settings": settings,
        "theme":    theme,
    }

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    conn = get_db()

    if request.method == "POST":
        action = request.form.get("action")

        # --- Save company info ---
        if action == "save_company":
            fields = [
                "company_name", "company_address", "company_phone",
                "company_email", "default_signatory"
            ]
            for field in fields:
                value = request.form.get(field, "").strip()
                conn.execute("""
                    INSERT INTO settings (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    updated_at=datetime('now')
                """, (field, value))

            # Handle logo upload separately
            logo = request.files.get("company_logo")
            if logo and logo.filename:
                ext      = os.path.splitext(logo.filename)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                    logo_dir  = os.path.join(BASE_DIR, "static", "uploads")
                    os.makedirs(logo_dir, exist_ok=True)
                    logo_path = os.path.join(logo_dir, f"company_logo{ext}")
                    logo.save(logo_path)
                    conn.execute("""
                        INSERT INTO settings (key, value) VALUES ('company_logo', ?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                        updated_at=datetime('now')
                    """, (f"company_logo{ext}",))
                else:
                    flash("Logo must be PNG, JPG, GIF or WEBP.", "danger")

            conn.commit()
            flash("Company info saved.", "success")

        # --- Save theme ---
        elif action == "save_theme":
            theme = request.form.get("theme", "navy")
            conn.execute("""
                INSERT INTO settings (key, value) VALUES ('theme', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                updated_at=datetime('now')
            """, (theme,))
            conn.commit()
            flash("Theme saved.", "success")

        # --- Add reference data item ---
        elif action == "add_ref":
            category = request.form.get("category", "").strip()
            value    = request.form.get("value", "").strip()
            if category and value:
                try:
                    conn.execute("""
                        INSERT INTO reference_data (category, value)
                        VALUES (?, ?)
                    """, (category, value))
                    conn.commit()
                    flash(f"Added '{value}' to {category}.", "success")
                except Exception:
                    flash(f"'{value}' already exists in {category}.", "warning")
            else:
                flash("Category and value are required.", "danger")

        # --- Delete reference data item ---
        elif action == "delete_ref":
            ref_id = request.form.get("ref_id")
            if ref_id:
                conn.execute(
                    "DELETE FROM reference_data WHERE id=?", (ref_id,)
                )
                conn.commit()
                flash("Item deleted.", "info")

        conn.close()
        return redirect(url_for("settings_page"))

    # GET — load everything
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in rows}

    ref_data = conn.execute("""
        SELECT * FROM reference_data ORDER BY category, sort_order, value
    """).fetchall()

    # Group reference data by category for the template
    from itertools import groupby
    ref_grouped = {}
    for row in ref_data:
        cat = row["category"]
        if cat not in ref_grouped:
            ref_grouped[cat] = []
        ref_grouped[cat].append(dict(row))

    conn.close()
    return render_template("settings.html",
                           settings=settings,
                           ref_grouped=ref_grouped)

@app.route("/")
def dashboard():
    conn = get_db()

    total_parts = conn.execute("SELECT COUNT(*) FROM parts WHERE is_traded=0 AND is_active=1").fetchone()[0]
    traded_parts   = conn.execute("SELECT COUNT(*) FROM parts WHERE is_traded=1 AND is_active=1").fetchone()[0]
    total_materials= conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    total_docs     = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    # Compliance summary
    def std_counts(standard):
        rows = conn.execute("""
            SELECT cs.status, COUNT(*) cnt FROM compliance_status cs
            JOIN parts p ON p.part_number = cs.part_number
            WHERE cs.standard=? AND p.is_active=1 AND p.is_traded=0
            GROUP BY cs.status
        """, (standard,)).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    rohs_counts     = std_counts("RoHS")
    reach_counts    = std_counts("REACH")
    pfas_counts     = std_counts("PFAS")
    montreal_counts = std_counts("Montreal Protocol")

    # Parts needing attention (any Unknown/Needs Review)
    needs_attention = conn.execute("""
        SELECT DISTINCT p.part_number, p.description
        FROM parts p
        JOIN compliance_status cs ON cs.part_number = p.part_number
        WHERE p.is_traded=0 AND p.is_active=1 AND cs.status IN ('Unknown','Needs Review','Contains PFAS','Contains SVHC','Contains ODS')
        LIMIT 10
    """).fetchall()

    # High risk materials
    high_risk_mats = conn.execute("""
        SELECT COUNT(*) FROM materials WHERE risk_level='High'
    """).fetchone()[0]
    pfas_mats = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE pfas_flag=1").fetchone()[0]

    recent_docs = conn.execute("""
        SELECT d.*, GROUP_CONCAT(dp.part_number, ', ') as parts_list
        FROM documents d
        LEFT JOIN document_parts dp ON dp.document_id = d.id
        GROUP BY d.id ORDER BY d.generated_at DESC LIMIT 8
    """).fetchall()

    last_import = conn.execute(
        "SELECT * FROM import_log ORDER BY imported_at DESC LIMIT 1"
    ).fetchone()

    conn.close()
    return render_template("dashboard.html",
        total_parts=total_parts, traded_parts=traded_parts,
        total_materials=total_materials, total_docs=total_docs,
        rohs_counts=rohs_counts, reach_counts=reach_counts,
        pfas_counts=pfas_counts, montreal_counts=montreal_counts,
        needs_attention=needs_attention, high_risk_mats=high_risk_mats,
        pfas_mats=pfas_mats, recent_docs=recent_docs,
        last_import=last_import)


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------

@app.route("/parts")
def parts_list():
    search   = request.args.get("search","").strip()
    cls_f    = request.args.get("cls","")
    status_f = request.args.get("status","")
    page     = int(request.args.get("page", 1))
    per_page = 50

    query  = """SELECT p.*,
        (SELECT cs.status FROM compliance_status cs
         WHERE cs.part_number=p.part_number AND cs.standard='RoHS' LIMIT 1) as rohs_status,
        (SELECT cs.status FROM compliance_status cs
         WHERE cs.part_number=p.part_number AND cs.standard='REACH' LIMIT 1) as reach_status,
        (SELECT cs.status FROM compliance_status cs
         WHERE cs.part_number=p.part_number AND cs.standard='PFAS' LIMIT 1) as pfas_status,
        (SELECT cs.status FROM compliance_status cs
         WHERE cs.part_number=p.part_number AND cs.standard='Montreal Protocol' LIMIT 1) as montreal_status,
        (SELECT COUNT(*) FROM fmd_files f
         WHERE f.part_number=p.part_number) as has_fmd
        FROM parts p WHERE p.is_traded=0 AND p.is_active=1 AND p.is_hidden=0"""
    params = []

    if search:
        query += " AND (p.part_number LIKE ? OR p.description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if cls_f:
        query += " AND p.part_class = ?"
        params.append(cls_f)

    # Count query is kept separate and simple — no compliance subqueries needed,
    # just count rows matching the same base filters
    count_q = "SELECT COUNT(*) FROM parts p WHERE p.is_traded=0 AND p.is_active=1 AND p.is_hidden=0"
    count_params = []
    if search:
        count_q += " AND (p.part_number LIKE ? OR p.description LIKE ?)"
        count_params += [f"%{search}%", f"%{search}%"]
    if cls_f:
        count_q += " AND p.part_class = ?"
        count_params.append(cls_f)

    conn = get_db()
    total_count = conn.execute(count_q, count_params).fetchone()[0]

    query += " ORDER BY p.part_number LIMIT ? OFFSET ?"
    params += [per_page, (page-1)*per_page]
    parts = conn.execute(query, params).fetchall()

    classes = conn.execute(
        "SELECT DISTINCT part_class FROM parts WHERE is_traded=0 AND part_class != '' ORDER BY part_class"
    ).fetchall()
    conn.close()

    total_pages = (total_count + per_page - 1) // per_page
    return render_template("parts.html", parts=parts, search=search,
                           cls_f=cls_f, status_f=status_f,
                           classes=classes, page=page,
                           total_pages=total_pages, total_count=total_count)

@app.route("/parts/traded")
def traded_parts():
    search = request.args.get("search","").strip()
    query  = "SELECT * FROM parts WHERE is_traded=1 AND is_hidden=0"
    params = []
    if search:
        query += " AND (part_number LIKE ? OR description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    query += " ORDER BY part_number"
    conn = get_db()
    parts = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("traded_parts.html", parts=parts, search=search)

@app.route("/parts/hidden")
def hidden_parts():
    conn = get_db()
    parts = conn.execute(
        "SELECT * FROM parts WHERE is_hidden=1 ORDER BY part_number"
    ).fetchall()
    conn.close()
    return render_template("hidden_parts.html", parts=parts)


@app.route("/parts/<path:part_number>/hide", methods=["POST"])
def hide_part(part_number):
    conn = get_db()
    conn.execute("UPDATE parts SET is_hidden=1 WHERE part_number=?", (part_number,))
    conn.commit()
    conn.close()
    flash("Part hidden.", "info")
    next_page = request.args.get("next")
    if next_page == "traded":
        return redirect(url_for("traded_parts"))
    return redirect(url_for("parts_list"))


@app.route("/parts/<path:part_number>/unhide", methods=["POST"])
def unhide_part(part_number):
    conn = get_db()
    conn.execute("UPDATE parts SET is_hidden=0 WHERE part_number=?", (part_number,))
    conn.commit()
    conn.close()
    flash("Part restored.", "success")
    return redirect(url_for("hidden_parts"))

@app.route("/parts/<path:part_number>/delete", methods=["POST"])
def delete_part(part_number):
    conn = get_db()

    # Check if part has linked data so we can warn in the flash message
    fmd = conn.execute(
        "SELECT id FROM fmd_files WHERE part_number=?", (part_number,)
    ).fetchone()
    docs = conn.execute(
        "SELECT COUNT(*) FROM document_parts WHERE part_number=?", (part_number,)
    ).fetchone()[0]

    # Delete from all related tables first (order matters — children before parent)
    conn.execute("DELETE FROM fmd_substances   WHERE part_number=?", (part_number,))
    conn.execute("DELETE FROM fmd_files        WHERE part_number=?", (part_number,))
    conn.execute("DELETE FROM compliance_status WHERE part_number=?", (part_number,))
    conn.execute("DELETE FROM document_parts   WHERE part_number=?", (part_number,))
    conn.execute("DELETE FROM bom_lines        WHERE parent_part=?", (part_number,))

    # Delete the FMD file from disk if it exists
    if fmd:
        fmd_record = conn.execute(
            "SELECT file_path FROM fmd_files WHERE part_number=?", (part_number,)
        ).fetchone()
        if fmd_record and os.path.exists(fmd_record["file_path"]):
            os.remove(fmd_record["file_path"])

    # Finally delete the part itself
    is_traded = conn.execute(
        "SELECT is_traded FROM parts WHERE part_number=?", (part_number,)
    ).fetchone()
    conn.execute("DELETE FROM parts WHERE part_number=?", (part_number,))

    conn.commit()
    conn.close()

    # Redirect to the right list depending on part type
    if is_traded and is_traded["is_traded"]:
        flash(f"Part {part_number} and all associated data deleted.", "info")
        return redirect(url_for("traded_parts"))
    else:
        flash(f"Part {part_number} and all associated data deleted.", "info")
        return redirect(url_for("parts_list"))

@app.route("/parts/<path:part_number>/edit", methods=["POST"])
def edit_part(part_number):
    new_part_number   = request.form.get("part_number", "").strip().upper()
    description       = request.form.get("description", "").strip()
    part_class        = request.form.get("part_class", "").strip()
    part_type         = request.form.get("part_type", "").strip()
    product_group     = request.form.get("product_group", "").strip()
    uom               = request.form.get("uom", "").strip()
    commodity_code    = request.form.get("commodity_code", "").strip()
    traded_vendor     = request.form.get("traded_vendor", "").strip()

    if not new_part_number:
        flash("Part number cannot be empty.", "danger")
        return redirect(url_for("part_detail", part_number=part_number))

    conn = get_db()

    # If part number changed, check for conflicts and update all references
    if new_part_number != part_number:
        existing = conn.execute(
            "SELECT id FROM parts WHERE part_number = ?", (new_part_number,)
        ).fetchone()
        if existing:
            conn.close()
            flash(f"Part number {new_part_number} already exists.", "warning")
            return redirect(url_for("part_detail", part_number=part_number))

        # Update all tables that reference this part number
        for table, column in [
            ("compliance_status", "part_number"),
            ("bom_lines",         "parent_part"),
            ("fmd_files",         "part_number"),
            ("fmd_substances",    "part_number"),
            ("document_parts",    "part_number"),
        ]:
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                (new_part_number, part_number)
            )

    # Update the part itself
    conn.execute("""
        UPDATE parts SET
            part_number    = ?,
            description    = ?,
            part_class     = ?,
            part_type      = ?,
            product_group  = ?,
            uom            = ?,
            commodity_code = ?,
            traded_vendor  = ?,
            updated_at     = datetime('now')
        WHERE part_number = ?
    """, (
        new_part_number, description, part_class, part_type,
        product_group, uom, commodity_code,
        traded_vendor or None, part_number
    ))

    conn.commit()
    conn.close()

    flash("Part updated successfully.", "success")
    return redirect(url_for("part_detail", part_number=new_part_number))

@app.route("/parts/new", methods=["POST"])
def new_part():
    part_number  = request.form.get("part_number", "").strip().upper()
    description  = request.form.get("description", "").strip()
    is_traded    = int(request.form.get("is_traded", 0))
    part_class   = request.form.get("part_class", "").strip()
    part_type    = request.form.get("part_type", "").strip()
    product_group= request.form.get("product_group", "").strip()
    uom          = request.form.get("uom", "").strip()
    commodity_code= request.form.get("commodity_code", "").strip()
    traded_vendor = request.form.get("traded_vendor", "").strip()

    # At least one of part_number or description is required
    if not part_number and not description:
        flash("Part number or description is required.", "danger")
        return redirect(request.referrer or url_for("parts_list"))

    # If no part number provided, auto-generate one from timestamp
    # so the part always has a valid URL-safe identifier
    if not part_number:
        from datetime import datetime
        part_number = "MANUAL-" + datetime.now().strftime("%Y%m%d%H%M%S")

    conn = get_db()

    # Check for duplicate
    existing = conn.execute(
        "SELECT id FROM parts WHERE part_number = ?", (part_number,)
    ).fetchone()
    if existing:
        conn.close()
        flash(f"Part {part_number} already exists.", "warning")
        return redirect(request.referrer or url_for("parts_list"))

    conn.execute("""
        INSERT INTO parts (
            part_number, description, part_class, part_type,
            product_group, uom, commodity_code, is_traded,
            traded_vendor, is_active, has_bom,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, datetime('now'), datetime('now'))
    """, (
        part_number, description, part_class, part_type,
        product_group, uom, commodity_code, is_traded,
        traded_vendor if is_traded else None
    ))

    conn.commit()
    conn.close()

    flash(f"Part {part_number} created successfully.", "success")
    # Send them straight to the detail page to continue setup
    return redirect(url_for("part_detail", part_number=part_number))

@app.route("/parts/<path:part_number>")
def part_detail(part_number):
    conn = get_db()
    part = conn.execute(
        "SELECT * FROM parts WHERE part_number=?", (part_number,)
    ).fetchone()
    if not part:
        flash("Part not found.", "danger")
        conn.close()
        return redirect(url_for("parts_list"))

    # BOM lines (direct children only)
    bom = conn.execute("""
        SELECT b.*, m.description as mat_desc, m.material_series,
               m.series_desc, m.primary_supplier, m.risk_level,
               m.pfas_flag, m.svhc_flag, m.ods_flag, m.rohs_flag
        FROM bom_lines b
        LEFT JOIN materials m ON m.part_number = b.material_part
        WHERE b.parent_part=? AND b.level=0
        ORDER BY b.sort_order
    """, (part_number,)).fetchall()

    # Compliance statuses
    statuses = conn.execute(
        "SELECT * FROM compliance_status WHERE part_number=?", (part_number,)
    ).fetchall()
    status_map = {r["standard"]: dict(r) for r in statuses}

    # Gaps
    gaps = get_compliance_gaps(part_number, conn)

    # Docs for this part
    docs = conn.execute("""
        SELECT d.* FROM documents d
        JOIN document_parts dp ON dp.document_id=d.id
        WHERE dp.part_number=?
        ORDER BY d.generated_at DESC
    """, (part_number,)).fetchall()

    # FMD file for this part
    fmd = conn.execute(
        "SELECT * FROM fmd_files WHERE part_number=?", (part_number,)
    ).fetchone()

     # Parsed substances from FMD
    fmd_substances = conn.execute("""
        SELECT material_name, substance_name, cas_number,
               substance_weight, substance_weight_uom,
               weight_on_hm_pct, weight_on_total_pct, hm_on_total_pct
        FROM fmd_substances
        WHERE part_number = ?
        ORDER BY material_name, weight_on_hm_pct DESC
    """, (part_number,)).fetchall()

    conn.close()
    return render_template("part_detail.html", part=part, bom=bom,
                           status_map=status_map, gaps=gaps, docs=docs, fmd=fmd, fmd_substances=fmd_substances)

@app.route("/parts/<path:part_number>/fmd/upload", methods=["POST"])
def upload_fmd(part_number):
    f = request.files.get("fmd_file")
    if not f or not f.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("part_detail", part_number=part_number))
    
    # --- Save the file ---
    safe_pn  = part_number.replace("/", "-")
    ext      = os.path.splitext(f.filename)[1]
    filename = f"{safe_pn}_FMD{ext}"
    filepath = os.path.join(FMD_DIR, filename)
    f.save(filepath)

    conn = get_db()

    # --- Record file in fmd_files ---
    # ON CONFLICT handles re-uploads — updates the record instead of
    # creating a duplicate
    conn.execute("""
        INSERT INTO fmd_files (part_number, filename, file_path)
        VALUES (?, ?, ?)
        ON CONFLICT(part_number)
        DO UPDATE SET filename=excluded.filename,
                      file_path=excluded.file_path,
                      uploaded_at=datetime('now')
    """, (part_number, filename, filepath))

    # --- Parse the PDF ---
    # parse_fmd_pdf returns a structured dict with manufacturer info
    # and a list of materials, each containing a list of substances
    try:
        fmd_data = parse_fmd_pdf(filepath)
    except Exception as e:
        conn.commit()
        conn.close()
        flash(f"File saved but could not be parsed: {e}", "warning")
        return redirect(url_for("part_detail", part_number=part_number))

    # --- Clear old substance rows for this part ---
    # If this is a re-upload we don't want stale data mixed with new data
    conn.execute(
        "DELETE FROM fmd_substances WHERE part_number = ?",
        (part_number,)
    )

    # --- Insert new substance rows ---
    # We flatten the nested structure: for each material, for each substance
    # under that material, insert one row into fmd_substances.
    # material_name is carried onto each substance row so the engine
    # can reference it in flag messages.
    all_substances = []

    for mat in fmd_data.get("materials", []):
        for sub in mat.get("substances", []):

            conn.execute("""
                INSERT INTO fmd_substances (
                    part_number, material_name, substance_name, cas_number,
                    substance_weight, substance_weight_uom,
                    weight_on_hm_pct, weight_on_total_pct, hm_on_total_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                part_number,
                mat["material_name"],
                sub["substance_name"],
                sub["cas_number"],
                sub["substance_weight"],
                sub["substance_weight_uom"],
                sub["weight_on_hm_pct"],
                sub["weight_on_total_pct"],
                mat["hm_on_total_pct"],
            ))

            # Build the flat list the compliance engine expects
            all_substances.append({
                "cas_number":          sub["cas_number"],
                "substance_name":      sub["substance_name"],
                "material_name":       mat["material_name"],
                "weight_on_hm_pct":    sub["weight_on_hm_pct"],
                "weight_on_total_pct": sub["weight_on_total_pct"],
            })

    # --- Run compliance determination ---
    # determine_compliance returns a dict of {standard: {status, flags}}
    # We write the status for each standard into compliance_status —
    # the same table the dashboard, parts list, and document generator
    # already read. Everything else updates automatically.
    if all_substances:
        compliance_results = determine_compliance(all_substances)

        for standard, result in compliance_results.items():
            notes = "; ".join(result["flags"]) if result["flags"] else None
            conn.execute("""
                INSERT INTO compliance_status
                    (part_number, standard, status, notes, last_assessed)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(part_number, standard)
                DO UPDATE SET status       = excluded.status,
                              notes        = excluded.notes,
                              last_assessed= excluded.last_assessed
            """, (part_number, standard, result["status"], notes))

    conn.commit()
    conn.close()

    substance_count = len(all_substances)
    flash(
        f"FMD parsed successfully — {substance_count} substance(s) extracted "
        f"and compliance status updated.",
        "success"
    )
    return redirect(url_for("part_detail", part_number=part_number))


@app.route("/parts/<path:part_number>/fmd/download")
def download_fmd(part_number):
    conn = get_db()
    fmd = conn.execute(
        "SELECT * FROM fmd_files WHERE part_number=?", (part_number,)
    ).fetchone()
    conn.close()
    if not fmd or not os.path.exists(fmd["file_path"]):
        flash("FMD file not found.", "danger")
        return redirect(url_for("part_detail", part_number=part_number))
    return send_file(fmd["file_path"], as_attachment=True, download_name=fmd["filename"])

# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

@app.route("/materials")
def materials_list():
    search   = request.args.get("search","").strip()
    risk_f   = request.args.get("risk","")
    flag_f   = request.args.get("flag","")
    page     = int(request.args.get("page",1))
    per_page = 50

    query  = "SELECT * FROM materials WHERE 1=1"
    params = []
    if search:
        query += " AND (part_number LIKE ? OR description LIKE ? OR primary_supplier LIKE ?)"
        params += [f"%{search}%"]*3
    if risk_f:
        query += " AND risk_level=?"
        params.append(risk_f)
    if flag_f == "pfas":
        query += " AND pfas_flag=1"
    elif flag_f == "svhc":
        query += " AND svhc_flag=1"
    elif flag_f == "ods":
        query += " AND ods_flag=1"
    elif flag_f == "rohs":
        query += " AND rohs_flag=1"

    conn = get_db()
    total_count = conn.execute(
        query.replace("SELECT *","SELECT COUNT(*)"), params
    ).fetchone()[0]
    query += " ORDER BY risk_level DESC, part_number LIMIT ? OFFSET ?"
    params += [per_page, (page-1)*per_page]
    mats = conn.execute(query, params).fetchall()
    conn.close()

    total_pages = (total_count + per_page - 1) // per_page
    return render_template("materials.html", materials=mats, search=search,
                           risk_f=risk_f, flag_f=flag_f,
                           page=page, total_pages=total_pages,
                           total_count=total_count)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method == "POST":
        import_type = request.form.get("import_type")
        f = request.files.get("file")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return redirect(url_for("import_data"))

        content = f.read().decode("latin-1")
        reader  = csv.DictReader(io.StringIO(content))

        conn = get_db()
        added = updated = skipped = 0

        if import_type == "part_list":
            added, updated, skipped = _import_part_list(reader, conn)
        elif import_type == "bom":
            added, updated, skipped = _import_bom(reader, conn)
        elif import_type == "po_listing":
            added, updated, skipped = _import_po_listing(reader, conn)

        conn.execute("""
            INSERT INTO import_log (import_type, filename, rows_added, rows_updated, rows_skipped)
            VALUES (?,?,?,?,?)
        """, (import_type, f.filename, added, updated, skipped))
        conn.commit()
        conn.close()

        flash(f"Import complete — {added} added, {updated} updated, {skipped} skipped.", "success")
        return redirect(url_for("import_data"))

    conn = get_db()
    logs = conn.execute(
        "SELECT * FROM import_log ORDER BY imported_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return render_template("import.html", logs=logs)


def _import_part_list(reader, conn):
    added = updated = skipped = 0
    traded_keywords = ["Asia Limited (I/CO", "Dongguan"]

    for row in reader:
        pn   = (row.get("Part","") or "").strip()
        if not pn:
            skipped += 1
            continue
        desc  = (row.get("Description","") or "").strip()
        is_active = 0 if "INACTIVE" in desc.upper() else 1
        cls   = (row.get("Part Class Desc","") or "").strip()
        ptype = (row.get("Type","") or "").strip()
        grp   = (row.get("Product Group Desc","") or "").strip()
        uom   = (row.get("Inventory UOM","") or "").strip()
        comm  = (row.get("Custom Tariff Code","") or "").strip()

        existing = conn.execute(
            "SELECT id FROM parts WHERE part_number=?", (pn,)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE parts SET description=?, part_class=?, part_type=?,
                product_group=?, uom=?, commodity_code=?, is_active=?, updated_at=datetime('now')
                WHERE part_number=?
            """, (desc, cls, ptype, grp, uom, comm, is_active, pn))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO parts (part_number, description, part_class, part_type,
                product_group, uom, commodity_code, is_active)
                VALUES (?,?,?,?,?,?,?,?)
            """, (pn, desc, cls, ptype, grp, uom, comm, is_active))
            added += 1

    conn.commit()
    return added, updated, skipped


def _import_bom(reader, conn):
    added = updated = skipped = 0

    for row in reader:
        parent = (row.get("Parent Part","") or "").strip()
        matl   = (row.get("Material Part","") or "").strip()
        if not parent or not matl:
            skipped += 1
            continue

        level  = int(row.get("Level","0") or 0)
        qty    = float(row.get("Qty/Parent","0") or 0)
        uom    = (row.get("Material Part UOM","") or "").strip()
        sort   = int(row.get("Mtl","0") or 0)

        mat_desc   = (row.get("Material_Desc","") or "").strip()
        mat_series = (row.get("Material Series","") or "").strip()
        series_desc= (row.get("Material Series Desc","") or "").strip()

        # Upsert material
        flags = assess_material_flags(mat_desc, mat_series)
        existing_mat = conn.execute(
            "SELECT id FROM materials WHERE part_number=?", (matl,)
        ).fetchone()
        if not existing_mat:
            conn.execute("""
                INSERT INTO materials (part_number, description, material_series,
                series_desc, uom, risk_level, pfas_flag, svhc_flag, ods_flag, rohs_flag)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (matl, mat_desc, mat_series, series_desc, uom,
                  flags["risk_level"], flags["pfas_flag"],
                  flags["svhc_flag"], flags["ods_flag"], flags["rohs_flag"]))

        # Upsert BOM line
        existing_bom = conn.execute("""
            SELECT id FROM bom_lines
            WHERE parent_part=? AND material_part=? AND level=?
        """, (parent, matl, level)).fetchone()

        if existing_bom:
            conn.execute("""
                UPDATE bom_lines SET qty_per_parent=?, uom=?, sort_order=?
                WHERE parent_part=? AND material_part=? AND level=?
            """, (qty, uom, sort, parent, matl, level))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO bom_lines (parent_part, material_part, level, qty_per_parent, uom, sort_order)
                VALUES (?,?,?,?,?,?)
            """, (parent, matl, level, qty, uom, sort))
            added += 1

        # Mark parent as having a BOM
        conn.execute(
            "UPDATE parts SET has_bom=1 WHERE part_number=?", (parent,)
        )

        # Auto-assess compliance for parent
        _auto_assess_part(parent, conn)

    conn.commit()
    return added, updated, skipped


def _import_po_listing(reader, conn):
    added = updated = skipped = 0

    for row in reader:
        pn      = (row.get("Part Num","") or "").strip()
        name    = (row.get("Name","") or "").strip()
        sup_id  = (row.get("Supplier ID","") or "").strip()
        desc    = (row.get("Description","") or "").strip()
        if not pn:
            skipped += 1
            continue

        # Upsert supplier
        if sup_id:
            conn.execute("""
                INSERT OR IGNORE INTO suppliers (supplier_id, name) VALUES (?,?)
            """, (sup_id, name))

        # Determine if traded
        is_traded = int(any(kw in name for kw in [
            "Asia Limited (I/CO", "Dongguan"
        ]))

        # Update material with supplier info
        conn.execute("""
            UPDATE materials SET primary_supplier=?, supplier_id=?, updated_at=datetime('now')
            WHERE part_number=? AND (primary_supplier IS NULL OR primary_supplier='')
        """, (name, sup_id, pn))

        # Update part traded flag
        if is_traded:
            conn.execute("""
                UPDATE parts SET is_traded=1, traded_vendor=?
                WHERE part_number=?
            """, (name, pn))

        added += 1

    conn.commit()
    return added, updated, skipped


def _auto_assess_part(part_number, conn):
    """Run automated compliance assessment and store results."""
    standards_map, _ = assess_part_compliance(part_number, conn)
    for std, status in standards_map.items():
        conn.execute("""
            INSERT INTO compliance_status (part_number, standard, status, last_assessed)
            VALUES (?,?,?,datetime('now'))
            ON CONFLICT(part_number, standard)
            DO UPDATE SET status=excluded.status, last_assessed=excluded.last_assessed
        """, (part_number, std, status))


# ---------------------------------------------------------------------------
# Document Generation
# ---------------------------------------------------------------------------

DOC_TYPES = ["RoHS", "REACH", "PFAS", "Montreal Protocol", "Combined (All Standards)"]


@app.route("/documents/generate", methods=["GET","POST"])
def generate_document():
    conn = get_db()

    if request.method == "POST":
        part_numbers = request.form.getlist("part_numbers")
        doc_type     = request.form.get("doc_type")
        customer     = request.form.get("customer","").strip()
        signatory    = request.form.get("signatory","").strip()
        company      = request.form.get("company","Schlegel Electronic Materials").strip()

        if not part_numbers:
            flash("Please select at least one part.", "danger")
            conn.close()
            return redirect(url_for("generate_document"))

        # Build per-part compliance data
        parts_data = []
        for pn in part_numbers:
            part = conn.execute(
                "SELECT * FROM parts WHERE part_number=?", (pn,)
            ).fetchone()
            if not part:
                continue

            statuses = conn.execute(
                "SELECT * FROM compliance_status WHERE part_number=?", (pn,)
            ).fetchall()
            status_map = {r["standard"]: dict(r) for r in statuses}

            # Get flagged materials for this part + standard
            flagged = []
            if doc_type in ("RoHS", "Combined (All Standards)"):
                flagged += conn.execute("""
                    SELECT DISTINCT m.part_number, m.description, m.primary_supplier
                    FROM bom_lines b JOIN materials m ON m.part_number=b.material_part
                    WHERE b.parent_part=? AND m.rohs_flag=1
                """, (pn,)).fetchall()
            if doc_type in ("REACH", "Combined (All Standards)"):
                flagged += conn.execute("""
                    SELECT DISTINCT m.part_number, m.description, m.primary_supplier
                    FROM bom_lines b JOIN materials m ON m.part_number=b.material_part
                    WHERE b.parent_part=? AND m.svhc_flag=1
                """, (pn,)).fetchall()
            if doc_type in ("PFAS", "Combined (All Standards)"):
                flagged += conn.execute("""
                    SELECT DISTINCT m.part_number, m.description, m.primary_supplier
                    FROM bom_lines b JOIN materials m ON m.part_number=b.material_part
                    WHERE b.parent_part=? AND m.pfas_flag=1
                """, (pn,)).fetchall()
            if doc_type in ("Montreal Protocol", "Combined (All Standards)"):
                flagged += conn.execute("""
                    SELECT DISTINCT m.part_number, m.description, m.primary_supplier
                    FROM bom_lines b JOIN materials m ON m.part_number=b.material_part
                    WHERE b.parent_part=? AND m.ods_flag=1
                """, (pn,)).fetchall()

            parts_data.append({
                "part_number": pn,
                "description": part["description"] or "",
                "status_map":  {k: v["status"] for k,v in status_map.items()},
                "flagged_materials": [dict(f) for f in flagged],
                "rohs_status":     status_map.get("RoHS", {}).get("status","Unknown") if status_map.get("RoHS") else "Unknown",
                "reach_status":    status_map.get("REACH", {}).get("status","Unknown") if status_map.get("REACH") else "Unknown",
                "pfas_status":     status_map.get("PFAS", {}).get("status","Unknown") if status_map.get("PFAS") else "Unknown",
                "montreal_status": status_map.get("Montreal Protocol", {}).get("status","Unknown") if status_map.get("Montreal Protocol") else "Unknown",
            })

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_type = doc_type.replace(" ","_").replace("(","").replace(")","")
        filename  = f"{safe_type}_{customer or 'NoCustomer'}_{timestamp}.pdf"
        file_path = os.path.join(DOCS_DIR, filename)

        # Build logo path from settings if a logo has been uploaded
        logo_filename = conn.execute(
            "SELECT value FROM settings WHERE key='company_logo'"
        ).fetchone()
        logo_path = None
        if logo_filename and logo_filename["value"]:
            logo_path = os.path.join(BASE_DIR, "static", "uploads", logo_filename["value"])

        generate_compliance_pdf(
            parts_data=parts_data,
            doc_type=doc_type,
            customer=customer,
            signatory=signatory,
            company=company,
            output_path=file_path,
            logo_path=logo_path,
        )

        doc_id = conn.execute("""
            INSERT INTO documents (doc_type, customer, signatory, company, file_path)
            VALUES (?,?,?,?,?)
        """, (doc_type, customer, signatory, company, file_path)).lastrowid

        for pn in part_numbers:
            status = "Unknown"
            cs = conn.execute(
                "SELECT status FROM compliance_status WHERE part_number=? AND standard=?",
                (pn, doc_type if doc_type != "Combined (All Standards)" else "RoHS")
            ).fetchone()
            if cs:
                status = cs["status"]
            conn.execute(
                "INSERT INTO document_parts (document_id, part_number, status) VALUES (?,?,?)",
                (doc_id, pn, status)
            )

        conn.commit()
        conn.close()
        flash(f"{doc_type} declaration generated for {len(part_numbers)} part(s).", "success")
        return redirect(url_for("documents_list"))

    # GET — load selectable parts (not traded, has BOM or has compliance data)
    parts = conn.execute("""
        SELECT p.part_number, p.description,
            (SELECT cs.status FROM compliance_status cs WHERE cs.part_number=p.part_number AND cs.standard='RoHS' LIMIT 1) as rohs_status,
            (SELECT cs.status FROM compliance_status cs WHERE cs.part_number=p.part_number AND cs.standard='REACH' LIMIT 1) as reach_status,
            (SELECT cs.status FROM compliance_status cs WHERE cs.part_number=p.part_number AND cs.standard='PFAS' LIMIT 1) as pfas_status,
            (SELECT cs.status FROM compliance_status cs WHERE cs.part_number=p.part_number AND cs.standard='Montreal Protocol' LIMIT 1) as montreal_status
        FROM parts p
        WHERE p.is_traded=0 AND p.is_active=1 AND p.is_hidden=0
        ORDER BY p.part_number
    """).fetchall()
    conn.close()
    return render_template("generate_document.html", parts=parts, doc_types=DOC_TYPES)


@app.route("/documents")
def documents_list():
    conn = get_db()
    docs = conn.execute("""
        SELECT d.*, GROUP_CONCAT(dp.part_number, ', ') as parts_list,
               COUNT(dp.id) as part_count
        FROM documents d
        LEFT JOIN document_parts dp ON dp.document_id=d.id
        GROUP BY d.id ORDER BY d.generated_at DESC
    """).fetchall()
    conn.close()
    return render_template("documents.html", docs=docs)


@app.route("/documents/<int:doc_id>/download")
def download_document(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not doc or not os.path.exists(doc["file_path"]):
        flash("File not found.", "danger")
        return redirect(url_for("documents_list"))
    return send_file(doc["file_path"], as_attachment=True,
                     download_name=os.path.basename(doc["file_path"]))


@app.route("/documents/<int:doc_id>/delete", methods=["POST"])
def delete_document(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if doc and doc["file_path"] and os.path.exists(doc["file_path"]):
        os.remove(doc["file_path"])
    conn.execute("DELETE FROM document_parts WHERE document_id=?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()
    flash("Document deleted.", "info")
    return redirect(url_for("documents_list"))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/part/<path:part_number>")
def api_part(part_number):
    conn = get_db()
    part = conn.execute("SELECT * FROM parts WHERE part_number=?", (part_number,)).fetchone()
    if not part:
        conn.close()
        return jsonify({}), 404
    statuses = conn.execute(
        "SELECT * FROM compliance_status WHERE part_number=?", (part_number,)
    ).fetchall()
    conn.close()
    data = dict(part)
    data["compliance"] = {r["standard"]: r["status"] for r in statuses}
    return jsonify(data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("\n" + "="*60)
    print("  Comply — Compliance Document Management System")
    print("  Running at: http://127.0.0.1:5000")
    print("="*60 + "\n")
    app.run(debug=True, port=5000)