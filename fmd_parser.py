"""
FMD Parser — Full Material Declaration PDF extraction
Supports the IPC-1752A tabular format used by Schlegel suppliers.
"""

import pdfplumber

def parse_fmd_pdf(path):
    """
    Parse an FMD PDF and return structured data.

    Returns a dict:
    {
        "manufacturer_name": str,
        "manufacturer_part_number": str,
        "customer_part_number": str,
        "total_weight": float,
        "total_weight_uom": str,
        "materials": [
            {
                "material_name": str,
                "material_weight": float,
                "material_weight_uom": str,
                "hm_on_total_pct": float,
                "substances": [
                    {
                        "substance_name": str,
                        "cas_number": str,
                        "substance_weight": float,
                        "substance_weight_uom": str,
                        "weight_on_hm_pct": float,
                        "weight_on_total_pct": float,
                    }
                ]
            }
        ]
    }
    """

    result = {
        "manufacturer_name":        None,
        "manufacturer_part_number": None,
        "customer_part_number":     None,
        "total_weight":             None,
        "total_weight_uom":         None,
        "materials":                []
    }

    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]

        # --- Extract header fields from raw text ---
        # The header rows sit above the table and aren't part of
        # the table structure, so we read them from the text stream.
        for line in page.extract_text().splitlines():
            if line.startswith("Manufacturer Name"):
                result["manufacturer_name"] = line.split("Manufacturer Name", 1)[1].strip()
            elif line.startswith("Manufacturer Part number"):
                result["manufacturer_part_number"] = line.split("Manufacturer Part number", 1)[1].strip()
            elif line.startswith("Customer Part number"):
                result["customer_part_number"] = line.split("Customer Part number", 1)[1].strip()

        # --- Extract substance table ---
        tables = page.extract_tables()
        if not tables:
            return result

        table = tables[0]

        # Find the column header row — it contains "Material Name"
        # We search rather than hardcode row 3 because different
        # supplier templates may have more or fewer header rows.
        header_row_idx = None
        for i, row in enumerate(table):
            if row and row[0] and "Material Name" in str(row[0]):
                header_row_idx = i
                break

        if header_row_idx is None:
            return result

        # Column layout (0-indexed):
        # 0  Material Name
        # 1  Material Weight
        # 2  Unit of Measurement
        # 3  Substance Name
        # 4  CAS Number
        # 5  Substance Weight
        # 6  Substance UOM
        # 7  Substance Weight on HM (%)
        # 8  Substance Weight on Total (%)
        # 9  HM on Total Weight (%)

        def to_float(val):
            # Strips whitespace and trailing % sign, returns None on failure.
            # We store raw percentages as floats, e.g. "3.33%" becomes 3.33
            if not val:
                return None
            try:
                return float(str(val).strip().rstrip('%'))
            except ValueError:
                return None

        current_material = None

        for row in table[header_row_idx + 1:]:

            # Skip completely blank rows (pdfplumber produces these
            # from merged/empty cells in the original table)
            if not any(c for c in row if c and str(c).strip()):
                continue

            mat_name = (row[0] or "").strip()

            # The last real row is the Total Weight summary — stop here
            if mat_name.lower().startswith("total weight"):
                try:
                    result["total_weight"]     = to_float(row[5])
                    result["total_weight_uom"] = (row[6] or "").strip()
                except IndexError:
                    pass
                break

            sub_name = (row[3] or "").strip()
            cas      = (row[4] or "").strip()

            # A new material row is identified by having a value in column 0.
            # Continuation rows (additional substances under the same material)
            # have None or "" in column 0 because that cell is merged in the PDF.
            if mat_name:
                current_material = {
                    "material_name":       mat_name,
                    "material_weight":     to_float(row[1]),
                    "material_weight_uom": (row[2] or "").strip(),
                    "hm_on_total_pct":     to_float(row[9]),
                    "substances":          []
                }
                result["materials"].append(current_material)

            # Add substance to the current material if this row has one.
            # This handles both: substance on the same row as the material,
            # and substance on a continuation row.
            if sub_name and current_material is not None:
                current_material["substances"].append({
                    "substance_name":       sub_name,
                    "cas_number":           cas,
                    "substance_weight":     to_float(row[5]),
                    "substance_weight_uom": (row[6] or "").strip(),
                    "weight_on_hm_pct":     to_float(row[7]),
                    "weight_on_total_pct":  to_float(row[8]),
                })

    return result