"""
PDF Compliance Declaration Generator
Generates multi-part supplier declarations for:
  RoHS / REACH / PFAS / Montreal Protocol / Combined
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import datetime

DARK_BLUE   = colors.HexColor("#1a3557")
MED_BLUE    = colors.HexColor("#2563a8")
LIGHT_BLUE  = colors.HexColor("#dbeafe")
GREEN       = colors.HexColor("#16a34a")
RED         = colors.HexColor("#dc2626")
AMBER       = colors.HexColor("#d97706")
GRAY_LIGHT  = colors.HexColor("#f1f5f9")
GRAY_BORDER = colors.HexColor("#cbd5e1")
WHITE       = colors.white


def _styles():
    s = {}
    s["title"] = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15,
        textColor=DARK_BLUE, alignment=TA_CENTER, spaceAfter=3)
    s["subtitle"] = ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10,
        textColor=MED_BLUE, alignment=TA_CENTER, spaceAfter=2)
    s["section"] = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=9,
        textColor=WHITE, leftIndent=6)
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=8.5,
        leading=13, alignment=TA_JUSTIFY, textColor=colors.black)
    s["label"] = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=7.5,
        textColor=colors.HexColor("#475569"))
    s["value"] = ParagraphStyle("value", fontName="Helvetica", fontSize=8.5,
        textColor=colors.black)
    s["footer"] = ParagraphStyle("footer", fontName="Helvetica-Oblique", fontSize=6.5,
        textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER)
    s["th"] = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8,
        textColor=WHITE)
    s["td"] = ParagraphStyle("td", fontName="Helvetica", fontSize=8,
        textColor=colors.black)
    s["td_bold"] = ParagraphStyle("td_bold", fontName="Helvetica-Bold", fontSize=8,
        textColor=colors.black)
    return s


def _section_hdr(text, styles, width):
    t = Table([[Paragraph(text, styles["section"])]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), MED_BLUE),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    return t


def _status_color(status):
    s = (status or "").lower()
    if any(w in s for w in ["compliant", "pfas-free", "free"]):
        return f'<font color="#16a34a"><b>{status}</b></font>'
    if any(w in s for w in ["non-compliant", "contains", "needs review"]):
        return f'<font color="#dc2626"><b>{status}</b></font>'
    if "exempt" in s:
        return f'<font color="#2563a8"><b>{status}</b></font>'
    return f'<font color="#d97706"><b>{status or "Unknown"}</b></font>'


def _doc_header(doc_type_label, customer, company, date_str, styles, width, story, logo_path=None):
    from reportlab.platypus import Image as RLImage

    # Build the left cell — logo if available, otherwise company name text
    if logo_path and os.path.exists(logo_path):
        try:
            logo = RLImage(logo_path, width=1.5*inch, height=0.5*inch)
            logo.hAlign = "LEFT"
            left_cell = logo
        except Exception:
            left_cell = Paragraph(f"<b>{company}</b>",
                ParagraphStyle("co", fontName="Helvetica-Bold", fontSize=12, textColor=DARK_BLUE))
    else:
        left_cell = Paragraph(f"<b>{company}</b>",
            ParagraphStyle("co", fontName="Helvetica-Bold", fontSize=12, textColor=DARK_BLUE))

    hdr_data = [[
        left_cell,
        Paragraph(f"<b>{doc_type_label}</b>",
            ParagraphStyle("dn", fontName="Helvetica-Bold", fontSize=11,
                           textColor=MED_BLUE, alignment=TA_CENTER)),
        Paragraph(f"Date: {date_str}<br/>Customer: {customer or '—'}",
            ParagraphStyle("ref", fontName="Helvetica", fontSize=8,
                           textColor=colors.HexColor("#475569"), alignment=TA_CENTER)),
    ]]
    t = Table(hdr_data, colWidths=[2.4*inch, 3.0*inch, width-5.4*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_BLUE),
        ("BOX",           (0,0),(-1,-1), 1.5, DARK_BLUE),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))


def _parts_summary_table(parts_data, doc_type, styles, width, story):
    """Table listing all parts with their compliance status for the selected standard."""
    story.append(_section_hdr("PRODUCTS COVERED BY THIS DECLARATION", styles, width))
    story.append(Spacer(1, 4))

    # Determine which status columns to show
    if doc_type == "Combined (All Standards)":
        headers = ["Part Number", "Description", "RoHS", "REACH", "PFAS", "Montreal"]
        col_w = [1.3*inch, 2.8*inch, 0.85*inch, 0.85*inch, 0.85*inch, 0.85*inch]
    else:
        headers = ["Part Number", "Description", "Status", "Flagged Materials"]
        col_w = [1.3*inch, 2.5*inch, 1.0*inch, width-4.8*inch]

    header_row = [Paragraph(h, styles["th"]) for h in headers]

    data_rows = []
    for p in parts_data:
        if doc_type == "Combined (All Standards)":
            row = [
                Paragraph(p["part_number"], styles["td_bold"]),
                Paragraph((p["description"] or "")[:55], styles["td"]),
                Paragraph(_status_color(p["rohs_status"]),
                    ParagraphStyle("sc", fontName="Helvetica-Bold", fontSize=7.5, alignment=TA_CENTER)),
                Paragraph(_status_color(p["reach_status"]),
                    ParagraphStyle("sc", fontName="Helvetica-Bold", fontSize=7.5, alignment=TA_CENTER)),
                Paragraph(_status_color(p["pfas_status"]),
                    ParagraphStyle("sc", fontName="Helvetica-Bold", fontSize=7.5, alignment=TA_CENTER)),
                Paragraph(_status_color(p["montreal_status"]),
                    ParagraphStyle("sc", fontName="Helvetica-Bold", fontSize=7.5, alignment=TA_CENTER)),
            ]
        else:
            # Single standard — pick relevant status
            std_key_map = {
                "RoHS": "rohs_status", "REACH": "reach_status",
                "PFAS": "pfas_status", "Montreal Protocol": "montreal_status",
            }
            status_key = std_key_map.get(doc_type, "rohs_status")
            status = p.get(status_key, "Unknown")
            flagged_names = ", ".join([
                f["part_number"] for f in p.get("flagged_materials", [])
            ]) or "None identified"
            row = [
                Paragraph(p["part_number"], styles["td_bold"]),
                Paragraph((p["description"] or "")[:55], styles["td"]),
                Paragraph(_status_color(status),
                    ParagraphStyle("sc", fontName="Helvetica-Bold", fontSize=7.5, alignment=TA_CENTER)),
                Paragraph(flagged_names[:100], styles["td"]),
            ]
        data_rows.append(row)

    table_data = [header_row] + data_rows
    t = Table(table_data, colWidths=col_w)
    row_bgs = [WHITE if i % 2 == 0 else GRAY_LIGHT for i in range(len(data_rows))]
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), DARK_BLUE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), row_bgs),
        ("GRID",          (0,0),(-1,-1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))


def _rohs_section(parts_data, styles, width, story):
    story.append(_section_hdr(
        "RoHS COMPLIANCE — EU Directive 2011/65/EU (amended by 2015/863/EU)", styles, width))
    story.append(Spacer(1, 4))

    # Overall status
    statuses = [p["rohs_status"] for p in parts_data]
    all_compliant = all("compliant" in (s or "").lower() and "non" not in (s or "").lower()
                        for s in statuses)
    any_flagged   = any("needs review" in (s or "").lower() or "non" in (s or "").lower()
                        for s in statuses)

    if all_compliant:
        decl = ("We hereby declare that all products listed above comply with EU Directive "
                "2011/65/EU on the Restriction of Hazardous Substances in Electrical and "
                "Electronic Equipment (RoHS), as amended by Directive 2015/863/EU (RoHS 3), "
                "and do not contain the restricted substances above maximum concentration values "
                "as defined in Annex II.")
    elif any_flagged:
        decl = ("One or more of the above products contain materials that have been flagged for "
                "RoHS review. The specific substances and affected materials are identified below. "
                "These products require further supplier documentation before a full compliance "
                "declaration can be issued.")
    else:
        decl = ("The RoHS compliance status for one or more listed products has not been fully "
                "determined. Material assessments are in progress.")

    story.append(Paragraph(decl, styles["body"]))
    story.append(Spacer(1, 6))

    # Restricted substances reference table
    substances = [
        ["Restricted Substance", "CAS No.", "Max Concentration"],
        ["Lead (Pb)",                        "7439-92-1",  "0.1 % (1000 ppm)"],
        ["Mercury (Hg)",                     "7439-97-6",  "0.1 % (1000 ppm)"],
        ["Cadmium (Cd)",                     "7440-43-9",  "0.01 % (100 ppm)"],
        ["Hexavalent Chromium (Cr VI)",       "18540-29-9", "0.1 % (1000 ppm)"],
        ["Polybrominated Biphenyls (PBB)",    "various",    "0.1 % (1000 ppm)"],
        ["Polybrominated Diphenyl Ethers (PBDE)", "various","0.1 % (1000 ppm)"],
        ["Bis(2-Ethylhexyl) Phthalate (DEHP)","117-81-7",  "0.1 % (1000 ppm)"],
        ["Benzyl Butyl Phthalate (BBP)",      "85-68-7",   "0.1 % (1000 ppm)"],
        ["Dibutyl Phthalate (DBP)",           "84-74-2",   "0.1 % (1000 ppm)"],
        ["Diisobutyl Phthalate (DIBP)",       "84-69-5",   "0.1 % (1000 ppm)"],
    ]
    col_w = [3.0*inch, 1.1*inch, width-4.1*inch]
    rows = [[Paragraph(c, styles["th"] if i==0 else styles["td"]) for c in row]
            for i, row in enumerate(substances)]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), DARK_BLUE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, GRAY_LIGHT]*6),
        ("GRID",          (0,0),(-1,-1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
    ]))
    story.append(t)

    # Flagged materials per part
    for p in parts_data:
        flagged = [f for f in p.get("flagged_materials", [])
                   if f.get("part_number")]
        if flagged:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"<b>Flagged Materials — {p['part_number']}:</b>", styles["body"]))
            for f in flagged:
                story.append(Paragraph(
                    f"  • {f['part_number']} — {f.get('description','')[:80]} "
                    f"(Supplier: {f.get('primary_supplier','Unknown')})",
                    styles["body"]))

    story.append(Spacer(1, 10))


def _reach_section(parts_data, styles, width, story):
    story.append(_section_hdr(
        "REACH COMPLIANCE — EC Regulation 1907/2006 (SVHC)", styles, width))
    story.append(Spacer(1, 4))

    statuses = [p["reach_status"] for p in parts_data]
    all_ok = all("compliant" in (s or "").lower() for s in statuses)

    if all_ok:
        decl = ("We hereby declare that all products listed above do not contain Substances of "
                "Very High Concern (SVHC) as listed on the ECHA Candidate List (Article 59(10) "
                "of REACH Regulation EC 1907/2006) at a concentration above 0.1% w/w.")
    else:
        decl = ("One or more of the above products contain materials that have been flagged as "
                "potential Substances of Very High Concern (SVHC). Supplier documentation is "
                "required to confirm or clear the flagged materials identified below.")

    story.append(Paragraph(decl, styles["body"]))
    story.append(Spacer(1, 6))

    for p in parts_data:
        flagged = [f for f in p.get("flagged_materials", []) if f.get("part_number")]
        if flagged:
            story.append(Paragraph(f"<b>SVHC-Flagged Materials — {p['part_number']}:</b>",
                                   styles["body"]))
            for f in flagged:
                story.append(Paragraph(
                    f"  • {f['part_number']} — {f.get('description','')[:80]}",
                    styles["body"]))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 8))


def _pfas_section(parts_data, styles, width, story):
    story.append(_section_hdr(
        "PFAS DECLARATION — Per- and Polyfluoroalkyl Substances", styles, width))
    story.append(Spacer(1, 4))

    statuses = [p["pfas_status"] for p in parts_data]
    all_free = all("free" in (s or "").lower() for s in statuses)
    any_contains = any("contains" in (s or "").lower() for s in statuses)

    if all_free:
        decl = ("We hereby confirm that all products listed above do not intentionally contain "
                "Per- and Polyfluoroalkyl Substances (PFAS), defined as any fluorinated compound "
                "containing at least one fully fluorinated methyl or methylene carbon atom. "
                "This declaration covers all components and sub-assemblies as supplied.")
    elif any_contains:
        decl = ("One or more products listed above contain Per- and Polyfluoroalkyl Substances "
                "(PFAS). The affected materials are identified below.")
    else:
        decl = ("PFAS assessment is pending for one or more listed products. "
                "Supplier data collection is in progress.")

    story.append(Paragraph(decl, styles["body"]))
    story.append(Spacer(1, 6))

    for p in parts_data:
        flagged = [f for f in p.get("flagged_materials", []) if f.get("part_number")]
        if flagged:
            story.append(Paragraph(f"<b>PFAS-Containing Materials — {p['part_number']}:</b>",
                                   styles["body"]))
            for f in flagged:
                story.append(Paragraph(
                    f"  • {f['part_number']} — {f.get('description','')[:80]} "
                    f"(Supplier: {f.get('primary_supplier','Unknown')})",
                    styles["body"]))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 8))


def _montreal_section(parts_data, styles, width, story):
    story.append(_section_hdr(
        "MONTREAL PROTOCOL — Ozone Depleting Substances (ODS)", styles, width))
    story.append(Spacer(1, 4))

    statuses = [p["montreal_status"] for p in parts_data]
    all_ok = all("compliant" in (s or "").lower() for s in statuses)

    if all_ok:
        decl = ("We hereby declare that all products listed above do not contain or use Ozone "
                "Depleting Substances (ODS) as defined by the Montreal Protocol on Substances "
                "that Deplete the Ozone Layer, including CFCs, HCFCs, Halons, carbon "
                "tetrachloride, methyl chloroform, methyl bromide, and HBFCs.")
    else:
        decl = ("One or more products listed above contain materials flagged for potential ODS "
                "content. Supplier verification is required for the materials identified below.")

    story.append(Paragraph(decl, styles["body"]))
    story.append(Spacer(1, 6))

    for p in parts_data:
        flagged = [f for f in p.get("flagged_materials", []) if f.get("part_number")]
        if flagged:
            story.append(Paragraph(f"<b>ODS-Flagged Materials — {p['part_number']}:</b>",
                                   styles["body"]))
            for f in flagged:
                story.append(Paragraph(
                    f"  • {f['part_number']} — {f.get('description','')[:80]}",
                    styles["body"]))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 8))


def generate_compliance_pdf(parts_data, doc_type, customer, signatory,
                             company, output_path, logo_path=None):
    """
    Generate a multi-part compliance declaration PDF.

    Args:
        parts_data: list of dicts with part_number, description,
                    rohs_status, reach_status, pfas_status, montreal_status,
                    flagged_materials
        doc_type:   RoHS / REACH / PFAS / Montreal Protocol / Combined (All Standards)
        customer:   Customer name
        signatory:  Authorized signer name
        company:    Manufacturer company name
        output_path: Full path for output PDF
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        rightMargin=0.6*inch, leftMargin=0.6*inch,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
    )
    width   = letter[0] - 1.2*inch
    styles  = _styles()
    story   = []
    date_str = datetime.now().strftime("%B %d, %Y")

    labels = {
        "RoHS":                   "RoHS Declaration of Conformity",
        "REACH":                  "REACH / SVHC Declaration",
        "PFAS":                   "PFAS-Free Declaration",
        "Montreal Protocol":      "Montreal Protocol / ODS Declaration",
        "Combined (All Standards)": "Combined Compliance Declaration",
    }
    label = labels.get(doc_type, f"{doc_type} Declaration")

    # Header
    _doc_header(label, customer, company, date_str, styles, width, story, logo_path=logo_path)

    # Products covered
    _parts_summary_table(parts_data, doc_type, styles, width, story)

    # Standard-specific sections
    if doc_type in ("RoHS", "Combined (All Standards)"):
        _rohs_section(parts_data, styles, width, story)
    if doc_type in ("REACH", "Combined (All Standards)"):
        _reach_section(parts_data, styles, width, story)
    if doc_type in ("PFAS", "Combined (All Standards)"):
        _pfas_section(parts_data, styles, width, story)
    if doc_type in ("Montreal Protocol", "Combined (All Standards)"):
        _montreal_section(parts_data, styles, width, story)

    # Disclaimer
    story.append(_section_hdr("DISCLAIMER", styles, width))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This declaration is based on information provided by our suppliers and internal "
        "material assessments. It reflects the status of the listed products as of the date "
        "indicated and is provided in good faith. This document does not constitute a warranty "
        "and may be subject to change if regulatory requirements or product compositions change. "
        "The issuing company assumes no liability for damages arising from reliance on this document.",
        styles["body"]))
    story.append(Spacer(1, 12))

    # Signature block
    story.append(_section_hdr("AUTHORIZED DECLARATION", styles, width))
    story.append(Spacer(1, 6))
    sig_data = [
        [Paragraph("Authorized Signatory:", styles["label"]),
         Paragraph("Title:", styles["label"]),
         Paragraph("Date:", styles["label"])],
        [Paragraph(signatory or "____________________", styles["value"]),
         Paragraph("Quality Compliance Manager", styles["value"]),
         Paragraph(date_str, styles["value"])],
        [Paragraph("Company:", styles["label"]),
         Paragraph("Signature:", styles["label"]),
         Paragraph("", styles["label"])],
        [Paragraph(company, styles["value"]),
         Paragraph("_________________________", styles["value"]),
         Paragraph("", styles["value"])],
    ]
    col_w = width / 3
    sig = Table(sig_data, colWidths=[col_w]*3)
    sig.setStyle(TableStyle([
        ("BOX",        (0,0),(-1,-1), 1, GRAY_BORDER),
        ("INNERGRID",  (0,0),(-1,-1), 0.5, GRAY_BORDER),
        ("BACKGROUND", (0,0),(-1,0), GRAY_LIGHT),
        ("BACKGROUND", (0,2),(-1,2), GRAY_LIGHT),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]))
    story.append(sig)
    story.append(Spacer(1, 8))

    # Footer
    story.append(HRFlowable(width=width, color=GRAY_BORDER, thickness=0.5))
    story.append(Spacer(1, 3))
    part_list = ", ".join([p["part_number"] for p in parts_data[:5]])
    if len(parts_data) > 5:
        part_list += f" +{len(parts_data)-5} more"
    story.append(Paragraph(
        f"Generated by Comply  |  {company}  |  {date_str}  |  "
        f"Standard: {doc_type}  |  Parts: {part_list}",
        styles["footer"]))

    doc.build(story)
    return output_path
