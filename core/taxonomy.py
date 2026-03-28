"""
Aureon Engine — Taxonomy Translation Layer
Practice-agnostic field mapping. Swap the dictionary.
Engine stays identical. Confidence scoring, edge case routing,
HITL-3 integration for low-confidence matches.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── PRACTICE DICTIONARIES ─────────────────────────────────────────────

ALADDIN = {
    "portfolio_id":     ["portfolio id","port id","fund id","account id","portfolio code"],
    "portfolio_name":   ["portfolio name","fund name","account name","strategy name"],
    "base_currency":    ["base currency","reporting currency","fund currency","home currency"],
    "benchmark":        ["benchmark","index","hurdle","reference index","comparator"],
    "aum":              ["aum","assets under management","nav","net asset value","fund size","market value","mv"],
    "inception_date":   ["inception date","launch date","start date","fund start"],
    "security_id":      ["security id","isin","cusip","sedol","ticker","ric","figi","sec id"],
    "security_name":    ["security name","instrument name","asset name","holding name"],
    "asset_class":      ["asset class","instrument type","security type","product type","asset type"],
    "sector":           ["sector","industry","gics sector","industry group","sub-sector"],
    "country":          ["country","country of risk","domicile","issuer country"],
    "currency":         ["currency","denomination","local currency","instrument currency","fx"],
    "maturity_date":    ["maturity date","expiry date","redemption date","final maturity"],
    "coupon":           ["coupon","coupon rate","interest rate","fixed rate","floating rate"],
    "rating":           ["rating","credit rating","moody rating","sp rating","fitch rating"],
    "quantity":         ["quantity","shares","units","par value","face value","nominal","notional"],
    "market_value":     ["market value","mv","mtm","mark to market","fair value","position value"],
    "weight":           ["weight","portfolio weight","allocation","pct weight","% of portfolio"],
    "cost_basis":       ["cost basis","book cost","average cost","purchase price","cost price"],
    "unrealized_pnl":   ["unrealized pnl","unrealised pnl","open pnl","paper gain","paper loss","mtm pnl","unrealized gain"],
    "trade_date":       ["trade date","transaction date","deal date","order date","execution date"],
    "settlement_date":  ["settlement date","value date","settle date","sd"],
    "trade_type":       ["trade type","transaction type","order type","side","buy sell"],
    "price":            ["price","trade price","execution price","fill price","clean price","dirty price"],
    "broker":           ["broker","counterparty","executing broker","prime broker","dealer"],
    "duration":         ["duration","modified duration","effective duration","dv01","pvbp"],
    "var":              ["var","value at risk","1 day var","99% var","parametric var"],
    "tracking_error":   ["tracking error","te","active risk","tracking risk","ex ante te"],
    "beta":             ["beta","market beta","equity beta","systematic risk"],
    "volatility":       ["volatility","vol","standard deviation","annualized vol","realized vol"],
    "limit_name":       ["limit","constraint","guideline","restriction","compliance rule"],
    "limit_value":      ["limit value","threshold","max","min","cap","floor","breach level"],
    "compliance_status":["compliant","breach","warning","pass fail","in breach"],
    "return":           ["return","performance","total return","net return","gross return","twr"],
    "alpha":            ["alpha","active return","excess return","outperformance"],
    "client_id":        ["client id","account number","customer id","investor id","entity id"],
    "client_name":      ["client name","investor name","account name","entity name"],
    "kyc_status":       ["kyc","kyc status","aml","due diligence","onboarding status"],
    "lei":              ["lei","legal entity identifier","bic","swift","entity code"],
}

FEDERAL = {
    "program_id":       ["program id","appropriation code","treas symbol","budget account","fund code"],
    "budget_authority": ["budget authority","obligations","outlays","apportionment","allotment","aum"],
    "compliance_status":["audit finding","material weakness","significant deficiency","noncompliance"],
    "client_id":        ["tin","uei","duns","cage code","vendor id","entity id"],
    "lei":              ["uei","sam registration","cage code"],
    "trade_date":       ["obligation date","award date","action date"],
    "market_value":     ["obligated amount","total award value","contract value"],
}

SIMCORP = {
    "portfolio_id":     ["dimension portfolio id","dim port","scd portfolio"],
    "security_id":      ["instrument id","dim instrument","scd instrument"],
    "trade_date":       ["transaction date","dim transaction"],
    "market_value":     ["position market value","dim mv"],
}

CHARLES_RIVER = {
    "portfolio_id":     ["crims portfolio","account code","cr account"],
    "security_id":      ["crims security id","cr instrument"],
    "trade_date":       ["order date","execution time"],
}

REGISTRIES = {
    "aladdin":       ALADDIN,
    "federal":       FEDERAL,
    "simcorp":       SIMCORP,
    "charles_river": CHARLES_RIVER,
}

def get_dictionary(practice: str = "aladdin") -> dict:
    return REGISTRIES.get(practice.lower(), ALADDIN)


# ── FIELD EXTRACTION ──────────────────────────────────────────────────

def extract_fields(text: str) -> list[str]:
    patterns = [
        r'\b([A-Z][a-zA-Z_ ]{2,30}(?:\s[A-Z][a-zA-Z]{2,15})?)\s*[:\|]',
        r'(?:column|field|attribute|property)\s*[:\"\']?\s*([a-zA-Z_][a-zA-Z0-9_ ]{2,30})',
        r'"([a-zA-Z_][a-zA-Z0-9_ ]{2,30})"',
        r'\b([a-z][a-z_]{2,20}(?:_id|_date|_type|_name|_value|_status|_code))\b',
    ]
    fields = set()
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            f = m.group(1).strip().lower().replace(' ', '_')
            if 3 < len(f) < 40:
                fields.add(f)
    return sorted(fields)


# ── SIMILARITY SCORING ────────────────────────────────────────────────

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def map_field(client_field: str, taxonomy: dict) -> dict:
    best_target, best_score, best_alias = None, 0.0, None
    cf = client_field.lower().replace('_',' ').replace('-',' ')
    for target, aliases in taxonomy.items():
        s = _sim(cf, target.replace('_',' '))
        if s > best_score:
            best_score, best_target, best_alias = s, target, target
        for alias in aliases:
            s = _sim(cf, alias.lower())
            if s > best_score:
                best_score, best_target, best_alias = s, target, alias

    from core.completeness import AUTO_THRESHOLD, REVIEW_THRESHOLD
    if best_score < 0.30:
        status = "no_match"
    elif best_score >= AUTO_THRESHOLD:
        status = "auto"
    elif best_score >= REVIEW_THRESHOLD:
        status = "review"    # → triggers HITL-3
    else:
        status = "no_match"

    return {
        "client_field":  client_field,
        "target_field":  best_target if status != "no_match" else None,
        "matched_via":   best_alias,
        "confidence":    round(best_score, 3),
        "status":        status,
        "hitl_required": status == "review",
    }

def run_mapping(fields: list[str], taxonomy: dict) -> dict:
    results = [map_field(f, taxonomy) for f in fields]
    auto    = [r for r in results if r["status"] == "auto"]
    review  = [r for r in results if r["status"] == "review"]
    no_match= [r for r in results if r["status"] == "no_match"]
    return {
        "total":         len(results),
        "auto":          len(auto),
        "review":        len(review),
        "no_match":      len(no_match),
        "pct_automated": round(len(auto) / max(len(results),1) * 100, 1),
        "hitl_required": len(review) > 0,
        "mappings":      results,
    }
