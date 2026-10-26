"""Mock extraction layer.

Row/column structure, labels, currencies and headline figures (total assets, excess of assets
over liabilities, SCR, own funds, solvency ratio, gross written premium for AXA UK) follow the
three sample filings. Everything else is generated, deterministic sample data. Replace
`extract()` with the real OpenAI-backed logic later; keep its return shape:

    {"meta": {...}, "templates": {"bs"|"lob"|"cty"|"tri"|"scr": DataFrame|None},
     "fields": DataFrame, "scr_chart": [(label, value, "relative"|"total"), ...]}
"""
from __future__ import annotations

import math
import random
import zlib

import pandas as pd

NAN = math.nan
IND = "   "

# Canonical template list (EIOPA codes); UK PRA filings use the IR.* equivalents.
TEMPLATES = [
    ("S.02.01.02", "Balance Sheet"),
    ("S.05.01.02", "Premiums, Claims & Expenses by Line of Business"),
    ("S.05.02.04", "Premiums, Claims & Expenses by Country"),
    ("S.19.01.21", "Non-Life Insurance Claims Information"),
    ("S.25.01 / S.25.05", "Solvency Capital Requirement"),
]

GROUP_LOBS = [
    "Medical expense", "Income protection", "Workers' compensation", "Motor vehicle liability",
    "Other motor", "Marine, aviation & transport", "Fire & other damage to property",
    "General liability", "Credit & suretyship", "Legal expenses", "Assistance",
    "Miscellaneous financial loss", "Non-prop. health re", "Non-prop. casualty re",
    "Non-prop. marine, aviation & transport re", "Non-prop. property re"]
GROUP_W = [5, 3, 1, 13, 15, 2, 20, 8, 3, 1.5, 2.5, 4, .3, 1.5, .5, 2]

# AXA UK column set (IR.05.04.02); weights are the gross written premiums read from the filing.
AXA_LOBS = [
    "Motor vehicle liability – personal", "Motor vehicle liability – non-personal",
    "Other motor – personal", "Other motor – non-personal", "Marine, aviation & transport",
    "Fire & other damage to property – personal", "Fire & other damage to property – non-personal",
    "General liability – employers' liability", "General liability – public & products liability",
    "Credit & suretyship", "Legal expenses", "Assistance", "Miscellaneous financial loss",
    "Non-prop. casualty re", "Non-prop. marine, aviation & transport re", "Non-prop. property re"]
AXA_W = [399.68, 357.04, 238.77, 151.60, 7.51, 370.16, 803.71, 109.34, 161.12, 1.09, 17.21,
         .17, 145.77, .0003, 0, 0]

_G = dict(group=True, codes=True, tri=False, lob_names=GROUP_LOBS, lob_w=GROUP_W, n_np=4,
          direct_share=.93, goodwill=False, report="Group SFCR – QRT annex", unit="k",
          unit_label="EUR thousand", ccy="EUR")

PROFILES = {
    "generali": {**_G, "entity": "Assicurazioni Generali S.p.A. – Generali Group",
                 "total_assets": 509_995_226, "excess": 51_497_932, "scr": 24_004_000,
                 "own_funds": 52_551_000, "gwp": 28_000_000, "life_share": .85,
                 "method": "Partial internal model", "numfmt": "1.234.567 (dot thousands)",
                 "countries": [("Italy", .338), ("Germany", .171), ("France", .160), ("Spain", .108),
                               ("Austria", .074), ("Portugal", .062)]},
    "allianz": {**_G, "entity": "Allianz SE – Allianz Group",
                "total_assets": 791_729_838, "scr": 43_259_437, "ratio": 2.18, "gwp": 62_000_000,
                "life_share": .85, "method": "Group internal model", "numfmt": "1,234,567",
                "countries": [("Germany", .264), ("France", .130), ("Italy", .111),
                              ("United Kingdom", .135), ("United States", .134), ("Australia", .086)]},
    "axa": dict(group=False, codes=False, tri=True, lob_names=AXA_LOBS, lob_w=AXA_W, n_np=3,
                direct_share=.9676, goodwill=True, report="UK PRA public QRTs (IR templates)",
                entity="AXA Insurance UK plc", ccy="GBP", unit="u", unit_label="GBP (whole pounds)",
                total_assets=6_160_176_384, excess=1_745_457_277, scr=1_099_582_399,
                own_funds=1_465_457_277, gwp=2_763_159_195, life_share=.03,
                method="Internal model", numfmt="1,234,567", countries=[("United Kingdom", .9606)]),
    "default": {**_G, "entity": "Sample Insurance Group (mock)", "total_assets": 42_000_000,
                "scr": 2_100_000, "ratio": 1.95, "gwp": 6_500_000, "life_share": .4,
                "method": "Standard formula", "numfmt": "1,234,567",
                "countries": [("Netherlands", .50), ("Belgium", .16), ("Germany", .11),
                              ("France", .07), ("Spain", .04), ("Italy", .02)]},
}

PERIOD = "31 Dec 2025"
VALUE_COL = "Solvency II value (C0010)"
TOTAL_COL = "Total"


def detect_profile(filename: str) -> dict:
    n = filename.lower()
    if "allianz" in n:
        return PROFILES["allianz"]
    if "axa" in n:
        return PROFILES["axa"]
    if "generali" in n or "sfcr ye25" in n:
        return PROFILES["generali"]
    return PROFILES["default"]


def _layout(p):
    if p["group"]:
        codes = ["S.02.01.02", "S.05.01.02", "S.05.02.04", "S.19.01.21", "S.25.05.22"]
        lob_t, scr_t = "Premiums, Claims & Expenses by Line of Business", "Solvency Capital Requirement – Internal Model (Partial or Full)"
    else:
        codes = ["IR.02.01.02", "IR.05.04.02", "IR.05.02.01", "IR.19.01.21", "IR.25.04.21"]
        lob_t, scr_t = "Non-life Income & Expenditure", "Solvency Capital Requirement – Internal Model"
    titles = ["Balance Sheet", lob_t, "Premiums, Claims & Expenses by Country",
              "Non-Life Insurance Claims Information", scr_t]
    return [dict(key=k, code=c, title=t, available=(k != "tri" or p["tri"]))
            for k, c, t in zip(["bs", "lob", "cty", "tri", "scr"], codes, titles)]


def _j(rng, lo=0.9, hi=1.1):
    return rng.uniform(lo, hi)


# ------------------------------------------------------------------ S.02.01 balance sheet
def _tp(r1, r2, r3, w):
    return [(r1, "Technical provisions calculated as a whole", w * .002),
            (r2, "Best estimate", w * .95), (r3, "Risk margin", w * .048)]


def _asset_tree(life, goodwill):
    t = []
    if goodwill:
        t += [("R0001", "Goodwill", .012), ("R0002", "Deferred acquisition costs", .004)]
    t += [
        ("R0030", "Intangible assets", .004), ("R0040", "Deferred tax assets", .004),
        ("R0050", "Pension benefit surplus", .0005),
        ("R0060", "Property, plant & equipment held for own use", .006),
        ("R0070", "Investments (other than assets held for index-linked and unit-linked contracts)", [
            ("R0080", "Property (other than for own use)", .02),
            ("R0090", "Holdings in related undertakings, including participations", .03),
            ("R0100", "Equities", [("R0110", "Equities – listed", .03), ("R0120", "Equities – unlisted", .01)]),
            ("R0130", "Bonds", [("R0140", "Government bonds", .30), ("R0150", "Corporate bonds", .18),
                                ("R0160", "Structured notes", .004), ("R0170", "Collateralised securities", .01)]),
            ("R0180", "Collective investments undertakings", .07), ("R0190", "Derivatives", .005),
            ("R0200", "Deposits other than cash equivalents", .01), ("R0210", "Other investments", .001)]),
        ("R0220", "Assets held for index-linked and unit-linked contracts", .12 * life),
        ("R0230", "Loans and mortgages", [("R0240", "Loans on policies", .002),
                                          ("R0250", "Loans and mortgages to individuals", .01),
                                          ("R0260", "Other loans and mortgages", .03)]),
        ("R0270", "Reinsurance recoverables from:", [
            ("R0280", "Non-life and health similar to non-life",
             [("R0290", "Non-life excluding health", .012), ("R0300", "Health similar to non-life", .001)]),
            ("R0310", "Life and health similar to life, excluding health and index-linked and unit-linked",
             [("R0320", "Health similar to life", .002), ("R0330", "Life excluding health and index-linked and unit-linked", .01 * life)]),
            ("R0340", "Life index-linked and unit-linked", .002 * life)]),
        ("R0350", "Deposits to cedants", .003), ("R0360", "Insurance and intermediaries receivables", .008),
        ("R0370", "Reinsurance receivables", .003), ("R0380", "Receivables (trade, not insurance)", .01),
        ("R0390", "Own shares (held directly)", .0002),
        ("R0400", "Amounts due in respect of own fund items or initial fund called up but not yet paid in", .0001),
        ("R0410", "Cash and cash equivalents", .02), ("R0420", "Any other assets, not elsewhere shown", .005)]
    return t


def _liab_tree(life):
    return [
        ("R0510", "Technical provisions – non-life", [
            ("R0520", "Technical provisions – non-life (excluding health)", _tp("R0530", "R0540", "R0550", .12 + .30 * (1 - life))),
            ("R0560", "Technical provisions – health (similar to non-life)", _tp("R0570", "R0580", "R0590", .01))]),
        ("R0600", "Technical provisions – life (excluding index-linked and unit-linked)", [
            ("R0610", "Technical provisions – health (similar to life)", _tp("R0620", "R0630", "R0640", .02 * life)),
            ("R0650", "Technical provisions – life (excluding health and index-linked and unit-linked)",
             _tp("R0660", "R0670", "R0680", .35 * life))]),
        ("R0690", "Technical provisions – index-linked and unit-linked", _tp("R0700", "R0710", "R0720", .12 * life)),
        ("R0740", "Contingent liabilities", .0003), ("R0750", "Provisions other than technical provisions", .004),
        ("R0760", "Pension benefit obligations", .006), ("R0770", "Deposits from reinsurers", .003),
        ("R0780", "Deferred tax liabilities", .012), ("R0790", "Derivatives", .004),
        ("R0800", "Debts owed to credit institutions", .008),
        ("R0810", "Financial liabilities other than debts owed to credit institutions", .01),
        ("R0820", "Insurance & intermediaries payables", .006), ("R0830", "Reinsurance payables", .004),
        ("R0840", "Payables (trade, not insurance)", .008),
        ("R0850", "Subordinated liabilities", [("R0860", "Subordinated liabilities not in basic own funds", .002),
                                               ("R0870", "Subordinated liabilities in basic own funds", .012)]),
        ("R0880", "Any other liabilities, not elsewhere shown", .008)]


def _leaves(tree):
    for n in tree:
        if isinstance(n[2], list):
            yield from _leaves(n[2])
        else:
            yield n


def _leaf_values(tree, target, rng):
    raw = {r: w * _j(rng) for r, _, w in _leaves(tree)}
    s = sum(raw.values())
    vals = {r: round(target * v / s) for r, v in raw.items()}
    vals[max(vals, key=vals.get)] += target - sum(vals.values())
    return vals


def _tree_rows(tree, vals, group, depth=0):
    rows, total = [], 0
    for ref, label, x in tree:
        ind = IND * depth
        if isinstance(x, list):
            sub, v = _tree_rows(x, vals, group, depth + 1)
            rows.append((ref, ind + label, v, depth == 0, depth == 0, group))
            rows.extend(sub)
        else:
            v = vals[ref]
            rows.append((ref, ind + label, v, False, depth == 0, group))
        total += v
    return rows, total


def _balance_sheet(p, rng, excess):
    life, ta = p["life_share"], p["total_assets"]
    at, lt = _asset_tree(life, p["goodwill"]), _liab_tree(life)
    av, lv = _leaf_values(at, ta, rng), _leaf_values(lt, ta - excess, rng)
    rows = [("", "ASSETS", NAN, True, False, "asset")]
    ar, _ = _tree_rows(at, av, "asset")
    rows += ar + [("R0500", "Total assets", ta, True, False, "asset"),
                  ("", "LIABILITIES", NAN, True, False, "liab")]
    lr, tl = _tree_rows(lt, lv, "liab")
    rows += lr + [("R0900", "Total liabilities", tl, True, False, "liab"),
                  ("R1000", "Excess of assets over liabilities", excess, True, False, "liab")]
    df = pd.DataFrame(rows, columns=["Ref", "Item", VALUE_COL, "_bold", "_top", "_group"])
    return df, ta, tl


# ------------------------------------------------------------------ S.05.01 / S.05.02
ROWS_05 = [
    ("R0110", "Premiums written – Gross – Direct business", False),
    ("R0120", "Premiums written – Gross – Proportional reinsurance accepted", False),
    ("R0130", "Premiums written – Gross – Non-proportional reinsurance accepted", False),
    ("R0140", "Premiums written – Reinsurers' share", False),
    ("R0200", "Premiums written – Net", True),
    ("R0210", "Premiums earned – Gross – Direct business", False),
    ("R0220", "Premiums earned – Gross – Proportional reinsurance accepted", False),
    ("R0230", "Premiums earned – Gross – Non-proportional reinsurance accepted", False),
    ("R0240", "Premiums earned – Reinsurers' share", False),
    ("R0300", "Premiums earned – Net", True),
    ("R0310", "Claims incurred – Gross – Direct business", False),
    ("R0320", "Claims incurred – Gross – Proportional reinsurance accepted", False),
    ("R0330", "Claims incurred – Gross – Non-proportional reinsurance accepted", False),
    ("R0340", "Claims incurred – Reinsurers' share", False),
    ("R0400", "Claims incurred – Net", True),
    ("R0550", "Expenses incurred", False),
    ("R1210", "Balance – other technical expenses/income", False),
    ("R1300", "Total technical expenses", True),
]
NP_NA = {"R0130", "R0230", "R0330"}                      # blank in proportional columns
PROP_NA = {"R0110", "R0120", "R0210", "R0220", "R0310", "R0320"}  # blank in non-proportional columns


def _financials(d, pr, n, share, rng):
    g = d + pr + n
    re = round(g * share)
    f = lambda: rng.uniform(.97, 1.0)
    ed, ep, en, ere = round(d * f()), round(pr * f()), round(n * f()), round(re * f())
    lr = rng.uniform(.5, .78)
    cd, cp, cn = round(ed * lr), round(ep * lr), round(en * lr)
    cre = round((cd + cp + cn) * share * rng.uniform(.8, 1.2))
    exp = round((ed + ep + en) * rng.uniform(.2, .3))
    bal = round(g * rng.uniform(-.01, .01))
    return {"R0110": d, "R0120": pr, "R0130": n, "R0140": re, "R0200": g - re,
            "R0210": ed, "R0220": ep, "R0230": en, "R0240": ere, "R0300": ed + ep + en - ere,
            "R0310": cd, "R0320": cp, "R0330": cn, "R0340": cre, "R0400": cd + cp + cn - cre,
            "R0550": exp, "R1210": bal, "R1300": exp + bal}


def _grid(colnames, cols, total_name, masks=None):
    rows = []
    for ref, label, bold in ROWS_05:
        vals = [NAN if masks and ref in masks[i] else cols[i][ref] for i in range(len(cols))]
        real = [v for v in vals if v == v]
        rows.append([ref, label, *vals, sum(real) if real else NAN, bold])
    return pd.DataFrame(rows, columns=["Ref", "Item", *colnames, total_name, "_bold"])


def _lob_table(p, rng):
    names, w, n_np = p["lob_names"], p["lob_w"], p["n_np"]
    cols, masks = [], []
    for i, wi in enumerate(w):
        g = p["gwp"] * wi / sum(w) * (_j(rng, .97, 1.03) if p["group"] else 1)
        is_np = i >= len(w) - n_np
        if is_np:
            d = pr = 0
            n = round(g)
        else:
            d = round(g * p["direct_share"])
            pr, n = round(g) - d, 0
        cols.append(_financials(d, pr, n, rng.uniform(.05, .25), rng))
        masks.append(PROP_NA if is_np else NP_NA)
    return _grid(names, cols, TOTAL_COL, masks)


def _country_table(p, lob, rng):
    tot = lob.set_index("Ref")[TOTAL_COL]
    cols, names = [], []
    for i, (name, sh) in enumerate(p["countries"]):
        d, pr, n = (round(tot[r] * sh * _j(rng, .98, 1.02)) if tot[r] == tot[r] else 0
                    for r in ("R0110", "R0120", "R0130"))
        cols.append(_financials(d, pr, n, rng.uniform(.05, .2), rng))
        names.append(f"Home country – {name}" if i == 0 else f"{name}")
    return _grid(names, cols, "Total top 5 and home country")


# ------------------------------------------------------------------ S.19.01 (AXA UK only)
def _triangle(p, rng):
    pattern = [.235, .155, .058, .045, .036, .022, .015, .011, .008, .005]
    devs = [f"Dev {d}" for d in range(10)]
    cols = ["Ref", "Accident year", *devs, "Dev 10 & +", "In current year", "Sum of years (cumulative)"]
    prior = round(p["gwp"] * .0087)
    rows = [["R0100", "Prior", *[NAN] * 10, prior, prior, prior, False]]
    for i in range(10):
        earned = p["gwp"] * (.81 + .019 * i) * _j(rng, .98, 1.02)
        vals = [round(earned * pattern[d] * _j(rng, .9, 1.1)) if d <= 9 - i else NAN for d in range(10)]
        paid = [v for v in vals if v == v]
        label = "N" if i == 9 else f"N-{9 - i}"
        rows.append([f"R{160 + 10 * i:04d}", label, *vals, NAN, paid[-1], sum(paid), False])
    df = pd.DataFrame(rows, columns=cols + ["_bold"])
    tot = ["R0260", "Total", *[df[c].sum(min_count=1) for c in cols[2:]], True]
    return pd.concat([df, pd.DataFrame([tot], columns=df.columns)], ignore_index=True)


# ------------------------------------------------------------------ S.25 SCR
def _scr_group(p, rng, S):
    life = p["life_share"]
    other, resid = round(.035 * S), round(.004 * S)
    cons = S - other - resid
    art4 = round(.00012 * S)
    pre = cons - art4
    U = round(pre / .8)
    div = pre - U
    raw = {"mc": .45, "ce": .02, "biz": .04, "nl": .20 * (1 - .5 * life), "lh": .05 + .2 * life,
           "op": .07, "oth": .02}
    sw = sum(raw.values())
    comp = {k: round(U * v / sw) for k, v in raw.items()}
    comp["mc"] += U - sum(comp.values())
    dv = {k: round(comp[k] * pre / U) for k in comp if k != "oth"}
    lac_tp, lac_dt = -round(.29 * S), -round(.23 * S)
    R = []
    R += [("", "Risk type", NAN, True), ("R0020", "Total diversification", div, False),
          ("R0030", "Total diversified risk before tax", pre, False),
          ("R0040", "Total diversified risk after tax", pre + lac_dt, False),
          ("R0070", "Total market & credit risk", comp["mc"], False),
          ("R0080", IND + "Market & credit risk – diversified", dv["mc"], False),
          ("R0190", "Credit event risk not covered in market & credit risk", comp["ce"], False),
          ("R0200", IND + "Credit event risk not covered in market & credit risk – diversified", dv["ce"], False),
          ("R0270", "Total business risk", comp["biz"], False),
          ("R0280", IND + "Total business risk – diversified", dv["biz"], False),
          ("R0310", "Total net non-life underwriting risk", comp["nl"], False),
          ("R0320", IND + "Total net non-life underwriting risk – diversified", dv["nl"], False),
          ("R0400", "Total life & health underwriting risk", comp["lh"], False),
          ("R0410", IND + "Total life & health underwriting risk – diversified", dv["lh"], False),
          ("R0480", "Total operational risk", comp["op"], False),
          ("R0490", IND + "Total operational risk – diversified", dv["op"], False),
          ("R0500", "Other risk", comp["oth"], False)]
    R += [("", "Calculation of Solvency Capital Requirement", NAN, True),
          ("R0110", "Total undiversified components", U, False), ("R0060", "Diversification", div, False),
          ("R0120", "Adjustment due to RFF/MAP nSCR aggregation", 0, False),
          ("R0160", "Capital requirement for business operated in accordance with Art. 4 of Directive 2003/41/EC", art4, False),
          ("R0200", "SCR calculated on the basis of Art. 336 (a) of Delegated Regulation (EU) 2015/35, excluding capital add-on", cons, False),
          ("R0210", "Capital add-ons already set", 0, False), ("R0220", "Consolidated Group SCR", cons, True)]
    R += [("", "Other information on SCR", NAN, True),
          ("R0310", "Overall loss-absorbing capacity of technical provisions", lac_tp, False),
          ("R0400", "Loss-absorbing capacity of deferred taxes", lac_dt, False),
          ("R0410", "Capital requirement for duration-based equity risk sub-module", 0, False),
          ("R0420", "Total notional SCR for remaining part", round(.93 * S), False),
          ("R0430", "Total notional SCR for ring-fenced funds", 0, False),
          ("R0440", "Total notional SCR for matching adjustment portfolios", round(.07 * S), False),
          ("", "Minimum consolidated Group SCR", round(.5 * S), False)]
    R += [("", "Information on other entities", NAN, True),
          ("", "Capital requirement for other financial sectors (non-insurance capital requirements)", other, False),
          ("", "Capital requirement for residual undertakings", resid, False),
          ("", "Overall SCR", S, False), ("", "SCR for undertakings included via D&A", 0, False),
          ("", "Total Group Solvency Capital Requirement", S, True)]
    chart = [("Market & credit", comp["mc"], "relative"), ("Credit event", comp["ce"], "relative"),
             ("Business", comp["biz"], "relative"), ("Non-life UW", comp["nl"], "relative"),
             ("Life & health UW", comp["lh"], "relative"), ("Operational", comp["op"], "relative"),
             ("Other", comp["oth"], "relative"), ("Diversification", div, "relative"),
             ("Art. 4 capital", art4, "relative"), ("Other fin. sectors", other, "relative"),
             ("Residual undertakings", resid, "relative"), ("Group SCR", S, "total")]
    return pd.DataFrame(R, columns=["Ref", "Item", "Amount (C0010)", "_bold"]), chart


def _scr_pra(p, rng, S):
    mods = {"Market risk": .44, "Counterparty default risk": .05, "Life underwriting risk": .02,
            "Total health underwriting risk": .005, "Non-life underwriting risk": .49}
    subs = {
        "Market risk": ([("Interest rate risk", .22), ("Equity risk", .10), ("Property risk", .14),
                         ("Spread risk", .30), ("Concentration risk", 0), ("Currency risk", .12),
                         ("Other market risk", .12)], .25),
        "Counterparty default risk": ([("Type 1 exposures", .7), ("Type 2 exposures", .1),
                                       ("Other counterparty risk", .2)], .12),
        "Life underwriting risk": ([("Mortality risk", .15), ("Longevity risk", .45), ("Life-expense risk", .15),
                                    ("Life catastrophe risk", .05), ("Other life underwriting risk", .2)], .2),
        "Total health underwriting risk": ([("Health catastrophe risk", 1)], 0),
        "Non-life underwriting risk": ([("Non-life premium and reserve risk (ex catastrophe risk)", .8),
                                        ("Non-life catastrophe risk", .3), ("Other non-life underwriting risk", .1)], .2),
    }
    bdiv = S / (.78 * 1.06 * .92)
    sw = sum(mods.values())
    M = {k: round(bdiv * w / sw) for k, w in mods.items()}
    sum_m = sum(M.values())
    div_m = -round(.22 * sum_m)
    after = sum_m + div_m
    op = round(.06 * after)
    lac_tp = 0
    lac_dt = -round(.08 * (after + op))
    lac_dt += S - (after + op + lac_tp + lac_dt)
    R = [("", "Net of loss-absorbing capacity of technical provisions", NAN, True)]
    for k, m in M.items():
        sl, d = subs[k]
        tw = sum(w for _, w in sl)
        vals = [round(m / (1 - d) * w / tw) for _, w in sl]
        R.append(("", k, m, True))
        R += [("", IND + n, v, False) for (n, _), v in zip(sl, vals)]
        R.append(("", IND + f"Diversification within {k.replace('Total ', '').lower()}", m - sum(vals), False))
    R += [("", "Intangible asset risk", 0, False),
          ("", "Total before diversification between risk modules", sum_m, False),
          ("", "Diversification between risk modules", div_m, False),
          ("", "Total after diversification", after, True),
          ("", "Operational and other risks", op, False), ("", IND + "Operational risk", op, False),
          ("", IND + "Other risks", 0, False),
          ("", "Loss-absorbing capacity of technical provisions", lac_tp, False),
          ("", "Loss-absorbing capacity of deferred taxes", lac_dt, False),
          ("", "Other adjustments", 0, False),
          ("", "Solvency capital requirement including undisclosed capital add-on", S, False),
          ("", "Disclosed capital add-on – excluding residual model limitation", 0, False),
          ("", "Disclosed capital add-on – residual model limitation", 0, False),
          ("", "Solvency capital requirement including capital add-on", S, True)]
    chart = [(k.replace(" underwriting risk", " UW").replace("Total health", "Health").replace(" default risk", ""),
              v, "relative") for k, v in M.items()]
    chart += [("Diversification", div_m, "relative"), ("After diversification", after, "total"),
              ("Operational", op, "relative"), ("LAC deferred tax", lac_dt, "relative"), ("SCR", S, "total")]
    return pd.DataFrame(R, columns=["Ref", "Item", "Amount (C0100)", "_bold"]), chart


# ------------------------------------------------------------------ assembly
def _flatten(templates, pages, rng):
    n = pages or 100
    recs = []
    for key, df in templates.items():
        if df is None:
            continue
        base = rng.randint(max(1, n // 2), n)
        vcols = [c for c in df.columns[2:] if not c.startswith("_")]
        for i, row in df.reset_index(drop=True).iterrows():
            for c in vcols:
                v = row[c]
                if pd.isna(v):
                    continue
                conf = rng.uniform(.70, .84) if rng.random() < .04 else rng.uniform(.86, .995)
                recs.append({"Template": key, "Row ref": row["Ref"], "Item": str(row[df.columns[1]]).strip(),
                             "Column": c, "Value": float(v), "Confidence": round(conf, 3),
                             "Source page": min(n, base + i // 12)})
    return pd.DataFrame(recs)


def extract(filename: str, pages: int | None = None) -> dict:
    """Single seam to replace with the real LLM extraction."""
    p = detect_profile(filename)
    rng = random.Random(zlib.crc32(p["entity"].encode()))
    own = p.get("own_funds") or round(p["scr"] * p["ratio"])
    excess = p.get("excess") or round(own * 1.05)
    bs, ta, tl = _balance_sheet(p, rng, excess)
    lob = _lob_table(p, rng)
    cty = _country_table(p, lob, rng)
    tri = _triangle(p, rng) if p["tri"] else None
    scr_df, chart = (_scr_group if p["group"] else _scr_pra)(p, rng, p["scr"])

    lt = lob.set_index("Ref")[TOTAL_COL]
    ct = cty.set_index("Ref")["Total top 5 and home country"]
    net_ok = all(int(lt[g1] + (lt[g2] if lt[g2] == lt[g2] else 0) + (lt[g3] if lt[g3] == lt[g3] else 0) - lt[sh]) == int(lt[net])
                 for g1, g2, g3, sh, net in (("R0110", "R0120", "R0130", "R0140", "R0200"),
                                              ("R0210", "R0220", "R0230", "R0240", "R0300")))
    cover = ct["R0110"] / lt["R0110"]
    checks = [
        ("Total assets − total liabilities = excess of assets over liabilities", ta - tl == excess),
        ("Gross − reinsurers' share = net (premiums written & earned, S.05.01 totals)", net_ok),
        (f"Home + top-5 countries cover {cover:.0%} of gross direct premiums written (≤ 100%)", cover <= 1.0),
        ("SCR build-up components sum to the reported SCR",
         abs(sum(v for _, v, m in chart if m == "relative") - p["scr"]) <= 1),
    ]
    if tri is not None:
        diag = sum(tri.iloc[i][[c for c in tri.columns if c.startswith("Dev")]].dropna().iloc[-1] for i in range(1, 11))
        checks.append(("Claims triangle diagonal equals 'in current year' total (S.19.01)",
                       int(diag) == int(tri.iloc[-1]["In current year"] - tri.iloc[0]["In current year"])))

    templates = {"bs": bs, "lob": lob, "cty": cty, "tri": tri, "scr": scr_df}
    if not p["codes"]:  # row codes of these sample templates could not be read reliably
        for k in ("bs", "lob", "scr"):
            templates[k] = templates[k].assign(Ref="")
    meta = dict(entity=p["entity"], report=p["report"], period=PERIOD, ccy=p["ccy"], unit=p["unit"],
                unit_label=p["unit_label"], method=p["method"], numfmt=p["numfmt"], pages=pages,
                codes=p["codes"], layout=_layout(p), total_assets=ta, excess=excess,
                gwp=int(lt["R0110"] + lt["R0120"]), scr=p["scr"], own_funds=own, ratio=own / p["scr"],
                checks=checks)
    return {"meta": meta, "templates": templates, "fields": _flatten(templates, pages, rng),
            "scr_chart": chart}
