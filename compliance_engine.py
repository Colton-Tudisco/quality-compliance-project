"""
Compliance Engine — CAS-number-based regulatory determination
Replaces keyword heuristics with authoritative reference table lookups.

Standards covered:
  - RoHS      EU Directive 2011/65/EU + 2015/863/EU (Annex II, 10 substances)
  - REACH     EC 1907/2006 SVHC Candidate List (Article 59)
  - PFAS      OECD/EPA per- and polyfluoroalkyl substance families
  - Montreal  Montreal Protocol Annex A/B/C/E ozone depleting substances
"""


# ---------------------------------------------------------------------------
# Reference Tables
# ---------------------------------------------------------------------------

# RoHS Annex II — CAS number → (human name, max concentration in ppm)
# Concentration is measured against the homogeneous material layer, not the
# whole article. 1000 ppm = 0.1%, 100 ppm = 0.01%
ROHS_SUBSTANCES = {
    "7439-92-1":  ("Lead (Pb)",                          1000),
    "7439-97-6":  ("Mercury (Hg)",                       1000),
    "7440-43-9":  ("Cadmium (Cd)",                        100),
    "18540-29-9": ("Hexavalent Chromium (Cr VI)",         1000),
    # PBB and PBDE are substance families — multiple CAS numbers each
    "59536-65-1": ("Polybrominated Biphenyls (PBB)",      1000),
    "32534-81-9": ("Decabromodiphenyl Ether (PBDE)",      1000),
    "36483-60-0": ("Octabromodiphenyl Ether (PBDE)",      1000),
    "40088-47-9": ("Hexabromodiphenyl Ether (PBDE)",      1000),
    # Phthalates added by RoHS 3 (2015/863/EU)
    "117-81-7":   ("Bis(2-Ethylhexyl) Phthalate (DEHP)", 1000),
    "85-68-7":    ("Benzyl Butyl Phthalate (BBP)",        1000),
    "84-74-2":    ("Dibutyl Phthalate (DBP)",             1000),
    "84-69-5":    ("Diisobutyl Phthalate (DIBP)",         1000),
}

# ECHA SVHC Candidate List (subset — most common in electronic/industrial parts)
# CAS number → reason for SVHC designation
# Full list: https://echa.europa.eu/candidate-list-table
# Threshold: >0.1% w/w of the total article
SVHC_CAS = {
    "7440-02-0":  "Nickel — respiratory sensitizer, suspected carcinogen",
    "7439-92-1":  "Lead — toxic to reproduction",
    "7440-43-9":  "Cadmium — carcinogenic, toxic to reproduction",
    "1333-86-4":  "Carbon Black — possible carcinogen (specific grades)",
    "80-05-7":    "Bisphenol A (BPA) — endocrine disruptor",
    "84-66-2":    "Diethyl phthalate — endocrine disruptor",
    "131-18-0":   "Dipentyl phthalate — toxic to reproduction",
    "605-50-5":   "Diisopentyl phthalate — toxic to reproduction",
    "7789-06-2":  "Strontium chromate — carcinogenic",
    "1306-19-0":  "Cadmium oxide — carcinogenic",
    "10108-64-2": "Cadmium chloride — carcinogenic",
    "7789-42-6":  "Cadmium bromide — carcinogenic",
    "7790-79-6":  "Cadmium fluoride — carcinogenic",
    "10124-36-4": "Cadmium sulphate — carcinogenic",
    "1306-23-6":  "Cadmium sulphide — carcinogenic",
    "18454-12-1": "Lead chromate molybdate — carcinogenic",
    "7758-97-6":  "Lead chromate — carcinogenic",
    "7446-14-2":  "Lead sulphate — toxic to reproduction",
    "15245-44-0": "Lead titanium zirconium oxide — toxic to reproduction",
    "12202-17-4": "Lead titanium trioxide — toxic to reproduction",
}

# PFAS — known CAS numbers for common PFAS compounds
# Plus name-based detection for the broader family
PFAS_CAS = {
    "9002-84-0":  "Polytetrafluoroethylene (PTFE/Teflon)",
    "25190-06-1": "Fluorinated ethylene propylene (FEP)",
    "24937-79-9": "Polyvinylidene fluoride (PVDF)",
    "28523-86-6": "Perfluorooctanoic acid (PFOA)",
    "1763-23-1":  "Perfluorooctanesulfonic acid (PFOS)",
    "355-46-4":   "Perfluorohexanesulfonic acid (PFHxS)",
    "375-95-1":   "Perfluorononanoic acid (PFNA)",
    "2058-94-8":  "Perfluorotetradecanoic acid",
    "376-06-7":   "Perfluorotetradecanoic acid isomer",
}

# Name fragments that indicate a PFAS compound even without a matched CAS.
# Used as a secondary check when CAS is "company proprietary" or missing.
PFAS_NAME_INDICATORS = [
    "fluoro", "fluorocarbon", "fluoropolymer", "ptfe", "teflon",
    "fep", "pvdf", "pfas", "pfoa", "pfos", "perfluoro", "polyfluoro",
    "hfp", "etfe", "pctfe",
]

# Montreal Protocol ODS — Annex A (CFCs), Annex B, Annex C (HCFCs), Annex E
ODS_CAS = {
    "75-69-4":   "Trichlorofluoromethane (CFC-11)",
    "75-71-8":   "Dichlorodifluoromethane (CFC-12)",
    "76-13-1":   "Trichlorotrifluoroethane (CFC-113)",
    "76-14-2":   "Dichlorotetrafluoroethane (CFC-114)",
    "76-15-3":   "Chloropentafluoroethane (CFC-115)",
    "75-45-6":   "Chlorodifluoromethane (HCFC-22)",
    "74-97-5":   "Bromochloromethane (Halon-1011)",
    "75-63-8":   "Bromotrifluoromethane (Halon-1301)",
    "74-83-9":   "Methyl bromide",
    "56-23-5":   "Carbon tetrachloride",
    "71-55-6":   "Methyl chloroform (1,1,1-trichloroethane)",
}


# ---------------------------------------------------------------------------
# Core determination function
# ---------------------------------------------------------------------------

def determine_compliance(substances):
    """
    Run all four regulatory checks against a list of substance dicts.

    Each substance dict is expected to have:
        cas_number          str   — may be "company proprietary" or empty
        substance_name      str
        weight_on_hm_pct    float — concentration in homogeneous material (%)
        weight_on_total_pct float — concentration in total article (%)
        material_name       str   — parent homogeneous material name

    Returns a dict:
    {
        "RoHS":             { "status": str, "flags": [str, ...] },
        "REACH":            { "status": str, "flags": [str, ...] },
        "PFAS":             { "status": str, "flags": [str, ...] },
        "Montreal Protocol":{ "status": str, "flags": [str, ...] },
    }

    Possible status values per standard:
        RoHS:             "Compliant"  | "Non-Compliant" | "Needs Review"
        REACH:            "Compliant"  | "Contains SVHC"
        PFAS:             "PFAS-Free"  | "Contains PFAS"
        Montreal Protocol:"Compliant"  | "Contains ODS"
    """

    results = {
        "RoHS":              {"status": "Compliant",  "flags": []},
        "REACH":             {"status": "Compliant",  "flags": []},
        "PFAS":              {"status": "PFAS-Free",  "flags": []},
        "Montreal Protocol": {"status": "Compliant",  "flags": []},
    }

    for sub in substances:
        cas         = (sub.get("cas_number")          or "").strip()
        name        = (sub.get("substance_name")       or "").strip()
        mat_name    = (sub.get("material_name")        or "").strip()
        pct_on_hm   = sub.get("weight_on_hm_pct")    or 0.0
        pct_on_total= sub.get("weight_on_total_pct")  or 0.0

        # --- RoHS ---
        # Check: is this CAS number a restricted substance, and is its
        # concentration in the homogeneous material above the threshold?
        # ppm threshold / 10000 converts ppm to a percentage.
        # e.g. 1000 ppm = 0.1% = threshold_pct of 0.1
        if cas in ROHS_SUBSTANCES:
            label, threshold_ppm = ROHS_SUBSTANCES[cas]
            threshold_pct = threshold_ppm / 10000
            if pct_on_hm > threshold_pct:
                results["RoHS"]["status"] = "Non-Compliant"
                results["RoHS"]["flags"].append(
                    f"{label} (CAS {cas}) at {pct_on_hm}% in '{mat_name}' "
                    f"— exceeds {threshold_ppm} ppm limit"
                )
            else:
                # Present but within limit — worth noting in the flags
                # so the declaration can acknowledge the substance exists
                results["RoHS"]["flags"].append(
                    f"{label} (CAS {cas}) present at {pct_on_hm}% in "
                    f"'{mat_name}' — within {threshold_ppm} ppm limit"
                )

        # --- REACH SVHC ---
        # Check: is this CAS on the Candidate List, and does it exceed
        # 0.1% w/w of the total article weight?
        if cas in SVHC_CAS:
            if pct_on_total > 0.1:
                results["REACH"]["status"] = "Contains SVHC"
                results["REACH"]["flags"].append(
                    f"{name} (CAS {cas}) — {SVHC_CAS[cas]} — "
                    f"{pct_on_total}% w/w of article (threshold: 0.1%)"
                )
            else:
                results["REACH"]["flags"].append(
                    f"{name} (CAS {cas}) — SVHC candidate, "
                    f"{pct_on_total}% w/w — below 0.1% threshold"
                )

        # --- PFAS ---
        # Two-pass check:
        # Pass 1: CAS number match against known PFAS compounds
        # Pass 2: Name-based match for compounds without a matched CAS
        #         (covers "company proprietary" entries and novel compounds)
        if cas in PFAS_CAS:
            results["PFAS"]["status"] = "Contains PFAS"
            results["PFAS"]["flags"].append(
                f"{PFAS_CAS[cas]} (CAS {cas}) in '{mat_name}'"
            )
        elif any(ind in name.lower() for ind in PFAS_NAME_INDICATORS):
            results["PFAS"]["status"] = "Contains PFAS"
            results["PFAS"]["flags"].append(
                f"{name} — PFAS indicator in substance name "
                f"(CAS: {cas or 'not provided'}) in '{mat_name}'"
            )
        # --- Montreal Protocol ---
        if cas in ODS_CAS:
            results["Montreal Protocol"]["status"] = "Contains ODS"
            results["Montreal Protocol"]["flags"].append(
                f"{name} (CAS {cas}) — {ODS_CAS[cas]}"
            )

    # --- Needs Review flag ---
    # If ANY substance has no CAS number (proprietary, blank, or unknown),
    # we can't fully certify RoHS or REACH — flag it for awareness.
    # This doesn't override a clean result, it appends a note.
    unknown_cas = [
        s.get("substance_name", "Unknown") for s in substances
        if not s.get("cas_number") or
           s.get("cas_number", "").lower() in ("", "company proprietary", "unknown", "n/a")
    ]
    if unknown_cas:
        note = f"CAS number not provided for: {', '.join(unknown_cas)} — manual verification recommended"
        results["RoHS"]["flags"].append(note)
        results["REACH"]["flags"].append(note)
        # Only escalate to Needs Review if currently showing clean
        if results["RoHS"]["status"] == "Compliant":
            results["RoHS"]["status"] = "Needs Review"
        if results["REACH"]["status"] == "Compliant":
            results["REACH"]["status"] = "Needs Review"

    return results