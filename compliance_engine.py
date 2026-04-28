"""
Compliance Engine — CAS-number-based regulatory determination

Standard versions (update these comments when reference data is updated):
  RoHS:             EU Directive 2011/65/EU + 2015/863/EU — Annex II
                    Current: 10 substances + 4 phthalates (RoHS 3, July 2019)
  REACH SVHC:       ECHA Candidate List — January 2025
                    Current: 247 substances total, partial CAS coverage included
  PFAS:             OECD/EPA broad definition — 2021
                    Current: CAS-based + name-indicator detection
  Montreal Protocol:Montreal Protocol Annex A/B/C/E — Kigali Amendment 2019
                    Current: CFCs, HCFCs, Halons, Methyl Bromide
  Cal Prop 65:      OEHHA Proposition 65 List — June 2024
                    Current: ~30 most common industrial/electronics substances
  China RoHS:       GB/T 26572-2011 — 6 restricted substances, Chinese market EEE
  TSCA:             EPA TSCA Section 6 — current rules through 2024
  Halogen-Free:     IEC 61249-2-21 / JEDEC JESD97 — Cl<900, Br<900, Total<1500 ppm

TODO (end of v1): Wire compliance checks to pull SVHC_CAS from regulatory_versions
                  + svhc_list DB tables. Add user notification banner on version update.
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

# California Proposition 65 — OEHHA list (June 2024 update)
# CAS number → "description (type)" — most common substances in electronics/industrial parts
# Full list: https://oehha.ca.gov/proposition-65/proposition-65-list
# Detection: CAS-match only. Status: "Compliant" | "Contains Prop 65 Substances"
PROP65_CAS = {
    "7439-92-1":  "Lead and lead compounds (reproductive toxin, developmental toxin)",
    "7439-97-6":  "Mercury and mercury compounds (reproductive toxin)",
    "7440-43-9":  "Cadmium and cadmium compounds (carcinogen)",
    "18540-29-9": "Hexavalent chromium compounds (carcinogen)",
    "117-81-7":   "Bis(2-Ethylhexyl) phthalate DEHP (reproductive toxin)",
    "85-68-7":    "Benzyl butyl phthalate BBP (reproductive toxin)",
    "84-74-2":    "Dibutyl phthalate DBP (reproductive toxin)",
    "84-69-5":    "Diisobutyl phthalate DIBP (reproductive toxin)",
    "80-05-7":    "Bisphenol A (BPA) — reproductive toxin",
    "71-43-2":    "Benzene (carcinogen)",
    "108-88-3":   "Toluene (developmental toxin, reproductive toxin)",
    "100-42-5":   "Styrene (carcinogen)",
    "75-09-2":    "Methylene chloride (carcinogen)",
    "79-01-6":    "Trichloroethylene TCE (carcinogen)",
    "127-18-4":   "Tetrachloroethylene PCE (carcinogen)",
    "56-23-5":    "Carbon tetrachloride (carcinogen)",
    "106-99-0":   "1,3-Butadiene (carcinogen)",
    "7440-38-2":  "Arsenic and inorganic arsenic compounds (carcinogen)",
    "7440-41-7":  "Beryllium and beryllium compounds (carcinogen)",
    "7440-02-0":  "Nickel and certain nickel compounds (carcinogen)",
    "1336-36-3":  "Polychlorinated biphenyls PCBs (carcinogen)",
    "1333-86-4":  "Carbon black (airborne, unbound — carcinogen)",
    "7664-93-9":  "Sulfuric acid (carcinogen)",
    "75-21-8":    "Ethylene oxide (carcinogen, reproductive toxin)",
    "1746-01-6":  "TCDD dioxin (carcinogen)",
    "309-00-2":   "Aldrin (carcinogen)",
    "50-29-3":    "DDT (carcinogen)",
    "60-57-1":    "Dieldrin (carcinogen)",
    "7789-06-2":  "Strontium chromate (carcinogen)",
    "96-45-7":    "Ethylene thiourea (carcinogen, developmental toxin)",
}

# China RoHS — GB/T 26572-2011 — 6 restricted substances for EEE sold in China
# CAS → (human name, threshold_ppm in homogeneous material)
# Same 6 base substances as EU RoHS; threshold differs only for Cd (100 ppm vs EU's 100 ppm — same)
# PBB/PBDE thresholds same as EU RoHS; all non-Cd thresholds are 1000 ppm
# Status: "Compliant" | "Non-Compliant" | "Needs Review"
CHINA_ROHS_SUBSTANCES = {
    "7439-92-1":  ("Lead (Pb)",                          1000),
    "7439-97-6":  ("Mercury (Hg)",                       1000),
    "7440-43-9":  ("Cadmium (Cd)",                        100),
    "18540-29-9": ("Hexavalent Chromium (Cr VI)",         1000),
    "59536-65-1": ("Polybrominated Biphenyls (PBB)",      1000),
    "32534-81-9": ("Decabromodiphenyl Ether (PBDE)",      1000),
}

# TSCA Section 6 — EPA restricted/prohibited substances (current through 2024)
# CAS → restriction description
# Detection: CAS-match only. Any match → "Restricted Substance Detected"
TSCA_CAS = {
    "1336-36-3":   "Polychlorinated biphenyls (PCBs) — prohibited manufacture/processing/distribution",
    "12001-28-4":  "Crocidolite asbestos — prohibited",
    "12172-73-5":  "Amosite asbestos — prohibited",
    "77536-66-4":  "Actinolite asbestos — prohibited",
    "77536-67-5":  "Anthophyllite asbestos — prohibited",
    "77536-68-6":  "Tremolite asbestos — prohibited",
    "132207-32-0": "Chrysotile asbestos — prohibited (2024 final rule)",
    "75-09-2":     "Methylene chloride — restricted consumer use (aerosol degreasing banned)",
    "1120-71-4":   "1,3-Propane sultone — restricted",
    "79-01-6":     "Trichloroethylene TCE — restricted use (vapor degreasing banned)",
    "127-18-4":    "Perchloroethylene PCE — restricted use",
    "14808-60-7":  "Silica, crystalline respirable — risk management rule active",
}

# Halogen-Free — IEC 61249-2-21 / JEDEC JESD97
# Thresholds: Cl < 900 ppm (0.09%), Br < 900 ppm (0.09%), Total halogens < 1500 ppm (0.15%)
# Measured against homogeneous material (weight_on_hm_pct)
# Status: "Halogen-Free" | "Contains Halogens" | "Needs Review"

# CAS numbers of predominantly chlorine-containing compounds
HALOGEN_CL_CAS = {
    "75-69-4",    # CFC-11 — also in ODS_CAS
    "75-71-8",    # CFC-12 — also in ODS_CAS
    "76-13-1",    # CFC-113 — also in ODS_CAS
    "56-23-5",    # Carbon tetrachloride
    "71-55-6",    # 1,1,1-trichloroethane
    "79-01-6",    # Trichloroethylene
    "127-18-4",   # Tetrachloroethylene
    "75-09-2",    # Methylene chloride
    "108-90-7",   # Chlorobenzene
    "67-66-3",    # Chloroform (trichloromethane)
    "75-00-3",    # Chloroethane
    "106-43-4",   # 4-Chlorotoluene
}

# CAS numbers of predominantly bromine-containing compounds
HALOGEN_BR_CAS = {
    "59536-65-1",  # PBB — also in RoHS/China RoHS
    "32534-81-9",  # DecaBDE — also in RoHS/China RoHS
    "36483-60-0",  # OctaBDE — also in RoHS
    "40088-47-9",  # HexaBDE — also in RoHS
    "79-94-7",     # TBBPA (tetrabromobisphenol A)
    "75-25-2",     # Bromoform
    "74-97-5",     # Bromochloromethane — also in ODS_CAS
    "75-63-8",     # Bromotrifluoromethane (Halon-1301) — also in ODS_CAS
    "74-83-9",     # Methyl bromide — also in ODS_CAS
    "75-26-3",     # 2-Bromopropane
    "75-27-4",     # Bromodichloromethane
}

# Name-based indicators for halogen detection when CAS is missing/proprietary
HALOGEN_CL_NAME_INDICATORS = [
    "chlor", "pvc", "polyvinyl chloride", "hcfc", "cfc", "pcb",
    "trichloroethyl", "perchloroethyl", "chloroform", "chlorobenz",
]
HALOGEN_BR_NAME_INDICATORS = [
    "brom", "pbde", "pbb", "tbbpa", "flame retard", "decabromodiphenyl",
    "brominated", "bromoform", "halon",
]


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
        "RoHS":              {"status": "Compliant",      "flags": []},
        "REACH":             {"status": "Compliant",      "flags": []},
        "PFAS":              {"status": "PFAS-Free",      "flags": []},
        "Montreal Protocol": {"status": "Compliant",      "flags": []},
        "Cal Prop 65":       {"status": "Compliant",      "flags": []},
        "China RoHS":        {"status": "Compliant",      "flags": []},
        "TSCA":              {"status": "Compliant",      "flags": []},
        "Halogen-Free":      {"status": "Halogen-Free",   "flags": []},
    }

    total_cl_ppm = 0.0
    total_br_ppm = 0.0

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

        # --- California Prop 65 ---
        if cas in PROP65_CAS:
            results["Cal Prop 65"]["status"] = "Contains Prop 65 Substances"
            results["Cal Prop 65"]["flags"].append(
                f"{name} (CAS {cas}) — {PROP65_CAS[cas]}"
            )

        # --- China RoHS ---
        if cas in CHINA_ROHS_SUBSTANCES:
            label, threshold_ppm = CHINA_ROHS_SUBSTANCES[cas]
            threshold_pct = threshold_ppm / 10000
            if pct_on_hm > threshold_pct:
                results["China RoHS"]["status"] = "Non-Compliant"
                results["China RoHS"]["flags"].append(
                    f"{label} (CAS {cas}) at {pct_on_hm}% in '{mat_name}' "
                    f"— exceeds {threshold_ppm} ppm limit (GB/T 26572)"
                )
            else:
                results["China RoHS"]["flags"].append(
                    f"{label} (CAS {cas}) present at {pct_on_hm}% in '{mat_name}'"
                    f" — within {threshold_ppm} ppm limit"
                )

        # --- TSCA Section 6 ---
        if cas in TSCA_CAS:
            results["TSCA"]["status"] = "Restricted Substance Detected"
            results["TSCA"]["flags"].append(
                f"{name} (CAS {cas}) — {TSCA_CAS[cas]}"
            )

        # --- Halogen-Free ---
        # Accumulate Cl/Br ppm from known halogenated substances and name indicators.
        # pct_on_hm is % of homogeneous material; multiply by 10000 to get ppm.
        if cas in HALOGEN_CL_CAS:
            total_cl_ppm += pct_on_hm * 10000
            results["Halogen-Free"]["flags"].append(
                f"Cl-containing: {name} (CAS {cas}) at {pct_on_hm:.4f}% HM"
            )
        elif any(ind in name.lower() for ind in HALOGEN_CL_NAME_INDICATORS):
            total_cl_ppm += pct_on_hm * 10000
            results["Halogen-Free"]["flags"].append(
                f"Cl-indicator in name: {name} at {pct_on_hm:.4f}% HM (CAS: {cas or 'not provided'})"
            )

        if cas in HALOGEN_BR_CAS:
            total_br_ppm += pct_on_hm * 10000
            results["Halogen-Free"]["flags"].append(
                f"Br-containing: {name} (CAS {cas}) at {pct_on_hm:.4f}% HM"
            )
        elif any(ind in name.lower() for ind in HALOGEN_BR_NAME_INDICATORS):
            total_br_ppm += pct_on_hm * 10000
            results["Halogen-Free"]["flags"].append(
                f"Br-indicator in name: {name} at {pct_on_hm:.4f}% HM (CAS: {cas or 'not provided'})"
            )

    # --- Halogen-Free final threshold evaluation ---
    total_halogen_ppm = total_cl_ppm + total_br_ppm
    if total_cl_ppm >= 900 or total_br_ppm >= 900 or total_halogen_ppm >= 1500:
        results["Halogen-Free"]["status"] = "Contains Halogens"
        results["Halogen-Free"]["flags"].insert(0,
            f"Cl: {total_cl_ppm:.0f} ppm, Br: {total_br_ppm:.0f} ppm, "
            f"Total: {total_halogen_ppm:.0f} ppm "
            f"(limits: Cl/Br <900 ppm, Total <1500 ppm — IEC 61249-2-21)"
        )
    elif total_cl_ppm > 0 or total_br_ppm > 0:
        results["Halogen-Free"]["flags"].insert(0,
            f"Cl: {total_cl_ppm:.0f} ppm, Br: {total_br_ppm:.0f} ppm — within limits"
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
        results["China RoHS"]["flags"].append(note)
        results["TSCA"]["flags"].append(note)
        results["Halogen-Free"]["flags"].append(note)
        # Only escalate to Needs Review if currently showing clean
        if results["RoHS"]["status"] == "Compliant":
            results["RoHS"]["status"] = "Needs Review"
        if results["REACH"]["status"] == "Compliant":
            results["REACH"]["status"] = "Needs Review"
        if results["China RoHS"]["status"] == "Compliant":
            results["China RoHS"]["status"] = "Needs Review"
        if results["TSCA"]["status"] == "Compliant":
            results["TSCA"]["status"] = "Needs Review"
        if results["Halogen-Free"]["status"] == "Halogen-Free":
            results["Halogen-Free"]["status"] = "Needs Review"

    return results