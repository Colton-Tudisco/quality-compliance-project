"""
PDF Compliance Certificate Generator
Generates professional compliance declarations for:
  - RoHS (EU Directive 2011/65/EU + amendment 2015/863)
  - REACH (EC Regulation 1907/2006)
  - PFAS (Per- and Polyfluoroalkyl Substances)
  - Montreal Protocol / ODS
  - Combined (all standards)
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import datetime


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
DARK_BLUE   = colors.HexColor("#1a3557")
MED_BLUE    = colors.HexColor("#2563a8")
LIGHT_BLUE  = colors.HexColor("#dbeafe")
GREEN       = colors.HexColor("#16a34a")
RED         = colors.HexColor("#dc2626")
AMBER       = colors.HexColor("#d97706")
GRAY_LIGHT  = colors.HexColor("#f1f5f9")
GRAY_BORDER = colors.HexColor("#cbd5e1")
WHITE       = colors.white


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["title"] = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=DARK_BLUE,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    styles["subtitle"] = ParagraphStyle(
        "subtitle",
        fontName="Helvetica",
        fontSize=11,
        textColor=MED_BLUE,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    styles["section_header"] = ParagraphStyle(
        "section_header",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=WHITE,
        alignment=TA_LEFT,
        leftIndent=6,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.black,
        leading=14,
        alignment=TA_JUSTIFY,
    )
    styles["body_bold"] = ParagraphStyle(
        "body_bold",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.black,
        leading=14,
    )
    styles["label"] = ParagraphStyle(
        "label",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=colors.HexColor("#475569"),
    )
    styles["value"] = ParagraphStyle(
        "value",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.black,
    )
    styles["footer"] = ParagraphStyle(
        "footer",
        fontName="Helvetica-Oblique",
        fontSize=7,
        textColor=colors.HexColor("#94a3b8"),
        alignment=TA_CENTER,
    )
    styles["status_compliant"] = ParagraphStyle(
        "status_compliant",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=GREEN,
        alignment=TA_CENTER,
    )
    styles["status_noncompliant"] = ParagraphStyle(
        "status_noncompliant",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=RED,
        alignment=TA_CENTER,
    )
    styles["status_unknown"] = ParagraphStyle(
        "status_unknown",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=AMBER,
        alignment=TA_CENTER,
    )
    return styles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section_header(text, styles, width):
    header_table = Table(
        [[Paragraph(text, styles["section_header"])]],
        colWidths=[width]
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MED_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    return header_table


def _info_table(rows, styles, width):
    """Two-column label/value table."""
    data = []
    for label, value in rows:
        data.append([
            Paragraph(label, styles["label"]),
            Paragraph(str(value) if value else "—", styles["value"]),
        ])
    t = Table(data, colWidths=[1.6*inch, width - 1.6*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
        ("GRID",       (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _status_badge(status):
    COMPLIANT_WORDS  = {"compliant", "pfas-free", "rohs compliant", "reach compliant"}
    NONCOMP_WORDS    = {"non-compliant", "contains svhc", "contains pfas", "contains ods"}
    s = status.lower()
    if any(w in s for w in COMPLIANT_WORDS):
        return f'<font color="#16a34a"><b>{status}</b></font>'
    if any(w in s for w in NONCOMP_WORDS):
        return f'<font color="#dc2626"><b>{status}</b></font>'
    if "exempt" in s:
        return f'<font color="#2563a8"><b>{status}</b></font>'
    return f'<font color="#d97706"><b>{status}</b></font>'


def _signature_block(signatory, company, date_str, styles, width):
    sig_data = [
        [
            Paragraph("Authorized Signatory:", styles["label"]),
            Paragraph("Title / Position:", styles["label"]),
            Paragraph("Date:", styles["label"]),
        ],
        [
            Paragraph(signatory or "____________________", styles["value"]),
            Paragraph("Quality Compliance Manager", styles["value"]),
            Paragraph(date_str, styles["value"]),
        ],
        [
            Paragraph("Company:", styles["label"]),
            Paragraph("Signature:", styles["label"]),
            Paragraph("", styles["label"]),
        ],
        [
            Paragraph(company, styles["value"]),
            Paragraph("_________________________", styles["value"]),
            Paragraph("", styles["value"]),
        ],
    ]
    col_w = width / 3
    t = Table(sig_data, colWidths=[col_w, col_w, col_w])
    t.setStyle(TableStyle([
        ("BOX",        (0, 0), (-1, -1), 1, GRAY_BORDER),
        ("INNERGRID",  (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), GRAY_LIGHT),
        ("BACKGROUND", (0, 2), (-1, 2), GRAY_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    return t


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------

def _build_header(part, doc_type_label, customer, company, date_str, styles, width, story):
    # Logo / company row
    hdr_data = [[
        Paragraph(f"<b>{company}</b>", ParagraphStyle(
            "co", fontName="Helvetica-Bold", fontSize=13, textColor=DARK_BLUE)),
        Paragraph(
            f"<b>{doc_type_label}</b>",
            ParagraphStyle("dname", fontName="Helvetica-Bold", fontSize=12,
                           textColor=MED_BLUE, alignment=TA_CENTER)),
        Paragraph(
            f"Date: {date_str}<br/>Doc#: {part['part_number']}-{datetime.now().strftime('%y%m%d')}",
            ParagraphStyle("ref", fontName="Helvetica", fontSize=8,
                           textColor=colors.HexColor("#475569"), alignment=TA_CENTER)),
    ]]
    hdr_t = Table(hdr_data, colWidths=[2.5*inch, 3*inch, width - 5.5*inch])
    hdr_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_BLUE),
        ("BOX",           (0, 0), (-1, -1), 1.5, DARK_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hdr_t)
    story.append(Spacer(1, 10))

    # Part info table
    story.append(_section_header("PRODUCT INFORMATION", styles, width))
    story.append(_info_table([
        ("Part Number",  part["part_number"]),
        ("Description",  part.get("description") or ""),
        ("Material",     part.get("material") or ""),
        ("Customer",     customer or part.get("customer") or ""),
        ("Manufacturer", company),
    ], styles, width))
    story.append(Spacer(1, 10))


def _build_rohs_section(part, styles, width, story):
    story.append(_section_header("RoHS COMPLIANCE — EU Directive 2011/65/EU (as amended by 2015/863)", styles, width))
    story.append(Spacer(1, 4))

    status = part.get("rohs_status", "Unknown")
    notes  = part.get("rohs_notes", "") or ""

    if "compliant" in status.lower() or "exempt" in status.lower():
        declaration = (
            "We hereby declare that the above-referenced product(s) comply with "
            "the requirements of EU Directive 2011/65/EU on the Restriction of the "
            "Use of Certain Hazardous Substances in Electrical and Electronic Equipment "
            "(RoHS), as amended by Directive 2015/863/EU (RoHS 3), and do not contain "
            "the following restricted substances above the maximum concentration values "
            "defined in Annex II:"
        )
    elif "non-compliant" in status.lower():
        declaration = (
            "The above-referenced product(s) do NOT fully comply with EU Directive "
            "2011/65/EU (RoHS). Please refer to the notes below for details on the "
            "specific restricted substances present."
        )
    else:
        declaration = (
            "The RoHS compliance status of the above-referenced product(s) has not "
            "been fully determined. An assessment is in progress."
        )

    story.append(Paragraph(declaration, styles["body"]))
    story.append(Spacer(1, 6))

    substances = [
        ["Restricted Substance", "CAS No.", "Max. Concentration", "Status"],
        ["Lead (Pb)",                   "7439-92-1",  "0.1% (1000 ppm)", _status_badge(status)],
        ["Mercury (Hg)",                "7439-97-6",  "0.1% (1000 ppm)", _status_badge(status)],
        ["Cadmium (Cd)",                "7440-43-9",  "0.01% (100 ppm)", _status_badge(status)],
        ["Hexavalent Chromium (Cr VI)", "18540-29-9", "0.1% (1000 ppm)", _status_badge(status)],
        ["Polybrominated Biphenyls (PBB)", "various", "0.1% (1000 ppm)", _status_badge(status)],
        ["Polybrominated Diphenyl Ethers (PBDE)", "various", "0.1% (1000 ppm)", _status_badge(status)],
        ["Bis(2-Ethylhexyl) Phthalate (DEHP)", "117-81-7", "0.1% (1000 ppm)", _status_badge(status)],
        ["Benzyl Butyl Phthalate (BBP)",  "85-68-7",  "0.1% (1000 ppm)", _status_badge(status)],
        ["Dibutyl Phthalate (DBP)",       "84-74-2",  "0.1% (1000 ppm)", _status_badge(status)],
        ["Diisobutyl Phthalate (DIBP)",   "84-69-5",  "0.1% (1000 ppm)", _status_badge(status)],
    ]

    col_w = [2.2*inch, 1.0*inch, 1.4*inch, width - 4.6*inch]
    sub_table = Table(
        [[Paragraph(c if i == 0 else c, ParagraphStyle(
            "th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE)) for i, c in enumerate(substances[0])]] +
        [[Paragraph(cell, ParagraphStyle("tc", fontName="Helvetica", fontSize=8)) if j != 3
          else Paragraph(cell, ParagraphStyle("ts", fontName="Helvetica-Bold", fontSize=8))
          for j, cell in enumerate(row)]
         for row in substances[1:]],
        colWidths=col_w
    )
    sub_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("ALIGN",         (3, 0), (3, -1), "CENTER"),
    ]))
    story.append(sub_table)

    if notes:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Notes:</b> {notes}", styles["body"]))

    story.append(Spacer(1, 10))


def _build_reach_section(part, styles, width, story):
    story.append(_section_header("REACH COMPLIANCE — EC Regulation 1907/2006", styles, width))
    story.append(Spacer(1, 4))

    status = part.get("reach_status", "Unknown")
    notes  = part.get("reach_notes", "") or ""

    if "compliant" in status.lower():
        declaration = (
            "We hereby declare that the above-referenced product(s) do not contain "
            "any Substances of Very High Concern (SVHC) as listed on the ECHA Candidate "
            "List (published under Article 59(10) of REACH Regulation EC 1907/2006) at "
            "a concentration above 0.1% w/w (weight by weight)."
        )
    elif "svhc" in status.lower():
        declaration = (
            "The above-referenced product(s) may contain one or more Substances of "
            "Very High Concern (SVHC) above 0.1% w/w. Please refer to the notes below "
            "for specific substance information. A full SVHC declaration is available "
            "upon request."
        )
    else:
        declaration = (
            "The REACH compliance status of the above-referenced product(s) is currently "
            "under assessment. A complete SVHC evaluation will be provided upon completion."
        )

    story.append(Paragraph(declaration, styles["body"]))
    story.append(Spacer(1, 6))

    reach_data = [
        [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE))
         for h in ["Assessment", "Standard", "Threshold", "Status"]],
        [
            Paragraph("SVHC Candidate List", styles["value"]),
            Paragraph("REACH Art. 59(10)", styles["value"]),
            Paragraph("0.1% w/w", styles["value"]),
            Paragraph(_status_badge(status),
                      ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=8)),
        ],
    ]
    col_w = [2.0*inch, 1.6*inch, 0.9*inch, width - 4.5*inch]
    t = Table(reach_data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("BACKGROUND",    (0, 1), (-1, 1), GRAY_LIGHT),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("ALIGN",         (3, 0), (3, -1), "CENTER"),
    ]))
    story.append(t)

    if notes:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Notes / SVHC Details:</b> {notes}", styles["body"]))

    story.append(Spacer(1, 10))


def _build_pfas_section(part, styles, width, story):
    story.append(_section_header("PFAS DECLARATION — Per- and Polyfluoroalkyl Substances", styles, width))
    story.append(Spacer(1, 4))

    status = part.get("pfas_status", "Unknown")
    notes  = part.get("pfas_notes", "") or ""

    if "free" in status.lower():
        declaration = (
            "We hereby confirm that the above-referenced product(s) do not intentionally "
            "contain Per- and Polyfluoroalkyl Substances (PFAS), a class of chemicals "
            "defined as any fluorinated compound containing at least one fully fluorinated "
            "methyl or methylene carbon atom. This declaration covers all components and "
            "subassemblies as supplied."
        )
    elif "contains" in status.lower():
        declaration = (
            "The above-referenced product(s) contain Per- and Polyfluoroalkyl Substances "
            "(PFAS). Please refer to the notes below for details on the specific substances "
            "present and their applications."
        )
    else:
        declaration = (
            "The PFAS status of the above-referenced product(s) is currently under "
            "assessment. Supplier data collection is in progress."
        )

    story.append(Paragraph(declaration, styles["body"]))
    story.append(Spacer(1, 6))

    pfas_data = [
        [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE))
         for h in ["Substance Group", "Definition", "Status"]],
        [
            Paragraph("PFAS (all)", styles["value"]),
            Paragraph("CnF(2n+1)— containing compounds", styles["value"]),
            Paragraph(_status_badge(status),
                      ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=8)),
        ],
    ]
    col_w = [1.5*inch, 3.5*inch, width - 5.0*inch]
    t = Table(pfas_data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("BACKGROUND",    (0, 1), (-1, 1), GRAY_LIGHT),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("ALIGN",         (2, 0), (2, -1), "CENTER"),
    ]))
    story.append(t)

    if notes:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Notes:</b> {notes}", styles["body"]))

    story.append(Spacer(1, 10))


def _build_montreal_section(part, styles, width, story):
    story.append(_section_header(
        "MONTREAL PROTOCOL — Ozone Depleting Substances (ODS) Declaration", styles, width))
    story.append(Spacer(1, 4))

    status = part.get("montreal_status", "Unknown")
    notes  = part.get("montreal_notes", "") or ""

    if "compliant" in status.lower():
        declaration = (
            "We hereby declare that the above-referenced product(s) do not contain "
            "or use Ozone Depleting Substances (ODS) as defined by the Montreal Protocol "
            "on Substances that Deplete the Ozone Layer and as controlled under the "
            "U.S. Clean Air Act. This includes CFCs, HCFCs, Halons, carbon tetrachloride, "
            "methyl chloroform, methyl bromide, and HBFCs."
        )
    elif "ods" in status.lower():
        declaration = (
            "The above-referenced product(s) contain or use Ozone Depleting Substances "
            "(ODS) as defined by the Montreal Protocol. Please refer to the notes below "
            "for details."
        )
    else:
        declaration = (
            "The ODS status of the above-referenced product(s) is currently under "
            "assessment."
        )

    story.append(Paragraph(declaration, styles["body"]))
    story.append(Spacer(1, 6))

    ods_data = [
        [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE))
         for h in ["Substance Class", "Examples", "Protocol", "Status"]],
        [Paragraph("Chlorofluorocarbons (CFCs)", styles["value"]),
         Paragraph("CFC-11, CFC-12, CFC-113", styles["value"]),
         Paragraph("Annex A", styles["value"]),
         Paragraph(_status_badge(status), ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=8))],
        [Paragraph("Hydrochlorofluorocarbons (HCFCs)", styles["value"]),
         Paragraph("HCFC-22, HCFC-141b", styles["value"]),
         Paragraph("Annex C", styles["value"]),
         Paragraph(_status_badge(status), ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=8))],
        [Paragraph("Halons", styles["value"]),
         Paragraph("Halon-1301, Halon-1211", styles["value"]),
         Paragraph("Annex B", styles["value"]),
         Paragraph(_status_badge(status), ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=8))],
        [Paragraph("Methyl Bromide", styles["value"]),
         Paragraph("CH₃Br", styles["value"]),
         Paragraph("Annex E", styles["value"]),
         Paragraph(_status_badge(status), ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=8))],
    ]
    col_w = [2.0*inch, 1.8*inch, 0.8*inch, width - 4.6*inch]
    t = Table(ods_data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("ALIGN",         (3, 0), (3, -1), "CENTER"),
    ]))
    story.append(t)

    if notes:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Notes:</b> {notes}", styles["body"]))

    story.append(Spacer(1, 10))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_compliance_pdf(part, doc_type, customer, signatory, company, output_path):
    """
    Generate a compliance certificate PDF.

    Args:
        part (dict): Part data from database
        doc_type (str): One of RoHS / REACH / PFAS / Montreal Protocol / Combined
        customer (str): Customer name
        signatory (str): Name of authorized signatory
        company (str): Manufacturer company name
        output_path (str): Full path for output PDF
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.65*inch,
        leftMargin=0.65*inch,
        topMargin=0.65*inch,
        bottomMargin=0.65*inch,
    )
    width = letter[0] - 1.3*inch

    styles = _build_styles()
    story  = []
    date_str = datetime.now().strftime("%B %d, %Y")

    # Map doc_type to label
    labels = {
        "RoHS":                   "RoHS Declaration of Conformity",
        "REACH":                  "REACH / SVHC Declaration",
        "PFAS":                   "PFAS-Free Declaration",
        "Montreal Protocol":      "Montreal Protocol / ODS Declaration",
        "Combined (All Standards)": "Combined Compliance Declaration",
    }
    label = labels.get(doc_type, f"{doc_type} Declaration")

    _build_header(part, label, customer, company, date_str, styles, width, story)

    if doc_type == "RoHS" or doc_type == "Combined (All Standards)":
        _build_rohs_section(part, styles, width, story)

    if doc_type == "REACH" or doc_type == "Combined (All Standards)":
        _build_reach_section(part, styles, width, story)

    if doc_type == "PFAS" or doc_type == "Combined (All Standards)":
        _build_pfas_section(part, styles, width, story)

    if doc_type == "Montreal Protocol" or doc_type == "Combined (All Standards)":
        _build_montreal_section(part, styles, width, story)

    # Legal disclaimer
    story.append(_section_header("DISCLAIMER", styles, width))
    story.append(Spacer(1, 4))
    disclaimer = (
        "This declaration is based on information provided by our suppliers and internal "
        "assessments. It reflects the status of the product(s) as of the date indicated. "
        "The information contained herein is provided in good faith and to the best of our "
        "knowledge. This document does not constitute a warranty and may be subject to change "
        "if regulatory requirements or product compositions change. The issuing company "
        "assumes no liability for any damages arising from reliance on this document."
    )
    story.append(Paragraph(disclaimer, styles["body"]))
    story.append(Spacer(1, 12))

    # Signature block
    story.append(_section_header("AUTHORIZED DECLARATION", styles, width))
    story.append(Spacer(1, 6))
    story.append(_signature_block(signatory, company, date_str, styles, width))
    story.append(Spacer(1, 8))

    # Footer
    story.append(HRFlowable(width=width, color=GRAY_BORDER, thickness=0.5))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generated by Quality Compliance Document Program  |  {company}  |  {date_str}  |  "
        f"Document type: {doc_type}  |  Part: {part['part_number']}",
        styles["footer"]
    ))

    doc.build(story)
    return output_path