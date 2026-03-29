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


def _entry(aliases, data_type, domain, entity_scope="general"):
    return {
        "aliases": aliases,
        "data_type": data_type,
        "domain": domain,
        "entity_scope": entity_scope,
    }


# ── PRACTICE DICTIONARIES ─────────────────────────────────────────────

ALADDIN = {
    "portfolio_id": _entry(
        ["portfolio id", "port id", "fund id", "account id", "portfolio code"],
        "identifier", "portfolio", "portfolio"
    ),
    "portfolio_name": _entry(
        ["portfolio name", "fund name", "account name", "strategy name"],
        "name", "portfolio", "portfolio"
    ),
    "base_currency": _entry(
        ["base currency", "reporting currency", "fund currency", "home currency"],
        "currency", "portfolio", "portfolio"
    ),
    "benchmark": _entry(
        ["benchmark", "index", "hurdle", "reference index", "comparator"],
        "identifier", "benchmark", "portfolio"
    ),
    "aum": _entry(
        ["aum", "assets under management", "fund size"],
        "amount", "portfolio", "portfolio"
    ),
    "inception_date": _entry(
        ["inception date", "launch date", "start date", "fund start"],
        "date", "portfolio", "portfolio"
    ),
    "security_id": _entry(
        ["security id", "isin", "cusip", "sedol", "ticker", "ric", "figi", "sec id"],
        "identifier", "security", "security"
    ),
    "security_name": _entry(
        ["security name", "instrument name", "asset name", "holding name"],
        "name", "security", "security"
    ),
    "asset_class": _entry(
        ["asset class", "instrument type", "security type", "product type", "asset type"],
        "category", "security", "security"
    ),
    "sector": _entry(
        ["sector", "industry", "gics sector", "industry group", "sub-sector"],
        "category", "security", "security"
    ),
    "country": _entry(
        ["country", "country of risk", "domicile", "issuer country"],
        "category", "security", "security"
    ),
    "currency": _entry(
        ["currency", "denomination", "local currency", "instrument currency", "fx"],
        "currency", "security", "security"
    ),
    "maturity_date": _entry(
        ["maturity date", "expiry date", "redemption date", "final maturity"],
        "date", "security", "security"
    ),
    "coupon": _entry(
        ["coupon", "coupon rate", "interest rate", "fixed rate", "floating rate"],
        "rate", "security", "security"
    ),
    "rating": _entry(
        ["rating", "credit rating", "moody rating", "sp rating", "fitch rating"],
        "category", "security", "security"
    ),
    "quantity": _entry(
        ["quantity", "shares", "units", "par value", "face value", "nominal", "notional"],
        "amount", "position", "position"
    ),
    "market_value": _entry(
        ["market value", "mv", "mtm", "mark to market", "fair value", "position value"],
        "amount", "position", "position"
    ),
    "weight": _entry(
        ["weight", "portfolio weight", "allocation", "pct weight", "% of portfolio"],
        "percentage", "position", "position"
    ),
    "cost_basis": _entry(
        ["cost basis", "book cost", "average cost", "purchase price", "cost price"],
        "amount", "position", "position"
    ),
    "unrealized_pnl": _entry(
        ["unrealized pnl", "unrealised pnl", "open pnl", "paper gain", "paper loss", "mtm pnl", "unrealized gain"],
        "amount", "position", "position"
    ),
    "trade_date": _entry(
        ["trade date", "transaction date", "deal date", "order date", "execution date"],
        "date", "trade", "trade"
    ),
    "settlement_date": _entry(
        ["settlement date", "value date", "settle date", "sd"],
        "date", "trade", "trade"
    ),
    "trade_type": _entry(
        ["trade type", "transaction type", "order type", "side", "buy sell"],
        "category", "trade", "trade"
    ),
    "price": _entry(
        ["price", "trade price", "execution price", "fill price", "clean price", "dirty price"],
        "amount", "trade", "trade"
    ),
    "broker": _entry(
        ["broker", "counterparty", "executing broker", "prime broker", "dealer", "broker code"],
        "identifier", "counterparty", "counterparty"
    ),
    "duration": _entry(
        ["duration", "modified duration", "effective duration", "dv01", "pvbp"],
        "metric", "risk", "security"
    ),
    "var": _entry(
        ["var", "value at risk", "1 day var", "99% var", "parametric var"],
        "metric", "risk", "portfolio"
    ),
    "tracking_error": _entry(
        ["tracking error", "te", "active risk", "tracking risk", "ex ante te"],
        "metric", "risk", "portfolio"
    ),
    "beta": _entry(
        ["beta", "market beta", "equity beta", "systematic risk"],
        "metric", "risk", "security"
    ),
    "volatility": _entry(
        ["volatility", "vol", "standard deviation", "annualized vol", "realized vol"],
        "metric", "risk", "portfolio"
    ),
    "limit_name": _entry(
        ["limit", "constraint", "guideline", "restriction", "compliance rule"],
        "name", "compliance", "rule"
    ),
    "limit_value": _entry(
        ["limit value", "threshold", "max", "min", "cap", "floor", "breach level"],
        "amount", "compliance", "rule"
    ),
    "compliance_status": _entry(
        ["compliant", "breach", "warning", "pass fail", "in breach"],
        "status", "compliance", "rule"
    ),
    "return": _entry(
        ["return", "performance", "total return", "net return", "gross return", "twr"],
        "percentage", "performance", "portfolio"
    ),
    "alpha": _entry(
        ["alpha", "active return", "excess return", "outperformance"],
        "percentage", "performance", "portfolio"
    ),
    "client_id": _entry(
        ["client id", "account number", "customer id", "investor id", "entity id"],
        "identifier", "client", "client"
    ),
    "client_name": _entry(
        ["client name", "investor name", "account name", "entity name"],
        "name", "client", "client"
    ),
    "kyc_status": _entry(
        ["kyc", "kyc status", "aml", "due diligence", "onboarding status"],
        "status", "client", "client"
    ),
    "lei": _entry(
        ["lei", "legal entity identifier", "bic", "swift", "entity code"],
        "identifier", "client", "client"
    ),
    # --- PATCH v1.1: explicit entries for fields missing from dictionary ---
    "custodian": _entry(
        ["custodian", "custodian name", "custodian bank", "safekeeping bank",
         "custody bank", "custodian_name", "sub-custodian"],
        "name", "counterparty", "counterparty"
    ),
    "corporate_action": _entry(
        ["corporate action", "corporate action type", "corporate_action_type",
         "ca type", "event type", "action type", "corporate event"],
        "category", "trade", "security"
    ),
    "corporate_action_id": _entry(
        ["corporate action id", "corporate_action_id", "ca id",
         "event id", "action id", "ca reference"],
        "identifier", "trade", "security"
    ),
    "order_id": _entry(
        ["order id", "order_id", "order reference", "order number",
         "ticket id", "instruction id"],
        "identifier", "trade", "trade"
    ),
    "trade_status": _entry(
        ["trade status", "trade_status", "order status", "execution status",
         "settlement status", "booking status", "lifecycle status"],
        "status", "trade", "trade"
    ),
    "position_date": _entry(
        ["position date", "position_date", "as of date", "valuation date",
         "pricing date", "holding date"],
        "date", "position", "position"
    ),
    "report_date": _entry(
        ["report date", "report_date", "reporting date", "statement date",
         "run date", "extraction date", "as at date"],
        "date", "event", "portfolio"
    ),
    "nav": _entry(
        ["nav", "net asset value", "fund nav", "total nav", "portfolio nav"],
        "amount", "portfolio", "portfolio"
    ),
    "abor_position": _entry(
        ["abor position", "abor_position", "accounting position",
         "accounting book of record", "abor balance"],
        "amount", "position", "position"
    ),
    "ibor_position": _entry(
        ["ibor position", "ibor_position", "investment position",
         "investment book of record", "ibor balance"],
        "amount", "position", "position"
    ),
    "recon_break": _entry(
        ["recon break", "recon_break_flag", "break flag", "reconciliation break",
         "position break", "cash break", "break indicator"],
        "status", "position", "position"
    ),
    "recon_break_amount": _entry(
        ["break amount", "break_amount", "recon break amount",
         "break value", "discrepancy amount"],
        "amount", "position", "position"
    ),
    "recon_break_reason": _entry(
        ["break reason", "break_reason", "recon break reason",
         "break description", "discrepancy reason", "break narrative"],
        "name", "position", "position"
    ),
    "sector_code": _entry(
        ["sector code", "sector_code", "gics code", "industry code",
         "sector classification", "sector id"],
        "identifier", "security", "security"
    ),
    "payment_date": _entry(
        ["payment date", "payment_date", "income date", "dividend date",
         "coupon payment date", "cash date"],
        "date", "trade", "security"
    ),
    "record_date": _entry(
        ["record date", "record_date", "holder of record date",
         "books close date", "ca record date"],
        "date", "trade", "security"
    ),
    "fund_code": _entry(
        ["fund code", "fund_code", "internal fund code", "strategy code",
         "fund identifier", "fund ref"],
        "identifier", "portfolio", "portfolio"
    ),
    "benchmark_id": _entry(
        ["benchmark id", "benchmark_id", "benchmark code", "index id",
         "reference index id", "comparator id"],
        "identifier", "benchmark", "portfolio"
    ),
}

FEDERAL = {
    "program_id": _entry(
        ["program id", "appropriation code", "treas symbol", "budget account", "fund code"],
        "identifier", "program", "program"
    ),
    "budget_authority": _entry(
        ["budget authority", "obligations", "outlays", "apportionment", "allotment", "aum"],
        "amount", "budget", "program"
    ),
    "compliance_status": _entry(
        ["audit finding", "material weakness", "significant deficiency", "noncompliance"],
        "status", "compliance", "rule"
    ),
    "client_id": _entry(
        ["tin", "uei", "duns", "cage code", "vendor id", "entity id"],
        "identifier", "vendor", "vendor"
    ),
    "lei": _entry(
        ["uei", "sam registration", "cage code"],
        "identifier", "vendor", "vendor"
    ),
    "trade_date": _entry(
        ["obligation date", "award date", "action date"],
        "date", "event", "program"
    ),
    "market_value": _entry(
        ["obligated amount", "total award value", "contract value"],
        "amount", "budget", "program"
    ),
}

SIMCORP = {
    "portfolio_id": _entry(
        ["dimension portfolio id", "dim port", "scd portfolio"],
        "identifier", "portfolio", "portfolio"
    ),
    "security_id": _entry(
        ["instrument id", "dim instrument", "scd instrument"],
        "identifier", "security", "security"
    ),
    "trade_date": _entry(
        ["transaction date", "dim transaction"],
        "date", "trade", "trade"
    ),
    "market_value": _entry(
        ["position market value", "dim mv"],
        "amount", "position", "position"
    ),
}

CHARLES_RIVER = {
    "portfolio_id": _entry(
        ["crims portfolio", "account code", "cr account"],
        "identifier", "portfolio", "portfolio"
    ),
    "security_id": _entry(
        ["crims security id", "cr instrument"],
        "identifier", "security", "security"
    ),
    "trade_date": _entry(
        ["order date", "execution time"],
        "date", "trade", "trade"
    ),
}

REGISTRIES = {
    "aladdin": ALADDIN,
    "federal": FEDERAL,
    "simcorp": SIMCORP,
    "charles_river": CHARLES_RIVER,
}


def get_dictionary(practice: str = "aladdin") -> dict:
    return REGISTRIES.get(practice.lower(), ALADDIN)


# ── FIELD EXTRACTION ──────────────────────────────────────────────────

def extract_fields(text: str) -> list[str]:
    patterns = [
        r"\b([A-Z][a-zA-Z_ ]{2,30}(?:\s[A-Z][a-zA-Z]{2,15})?)\s*[:\|]",
        r"(?:column|field|attribute|property)\s*[:\"\']?\s*([a-zA-Z_][a-zA-Z0-9_ ]{2,30})",
        r"\"([a-zA-Z_][a-zA-Z0-9_ ]{2,30})\"",
        r"\b([a-z][a-z_]{2,20}(?:_id|_date|_type|_name|_value|_status|_code))\b",
    ]
    fields = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            field_name = match.group(1).strip().lower().replace(" ", "_")
            if 3 < len(field_name) < 40:
                fields.add(field_name)
    return sorted(fields)


# ── SEMANTIC GUARDRAILS ───────────────────────────────────────────────

TYPE_KEYWORDS = {
    "identifier": ("_id", " id", "code", "number", "num", "key", "identifier", "lei", "isin", "cusip", "sedol", "figi", "ticker"),
    "date": ("_date", " date", "maturity", "settlement", "trade date", "report date", "as of", "effective"),
    "status": ("_status", " status", "state", "stage", "flag"),
    "name": ("_name", " name", "title", "description", "label"),
    "amount": ("_value", " amount", "value", "price", "cost", "pnl", "aum", "mv", "quantity", "balance", "notional"),
    "currency": ("currency", "ccy", "fx"),
    "percentage": ("weight", "pct", "%", "percent", "ratio", "alpha", "return"),
    "rate": ("coupon", "rate", "yield", "spread"),
    "category": ("type", "class", "sector", "country", "side"),
}

DOMAIN_KEYWORDS = {
    "portfolio": ("portfolio", "fund", "account", "strategy", "benchmark", "aum", "nav"),
    "security": ("security", "instrument", "asset", "issuer", "maturity", "coupon", "rating", "isin", "cusip", "ticker"),
    "position": ("position", "holding", "market value", "book cost", "weight", "quantity"),
    "trade": ("trade", "order", "execution", "settlement"),
    "counterparty": ("broker", "dealer", "counterparty", "custodian", "prime broker"),
    "client": ("client", "investor", "customer", "entity", "kyc", "aml"),
    "compliance": ("compliance", "limit", "guideline", "restriction", "breach"),
    "performance": ("performance", "return", "alpha", "benchmark"),
    "risk": ("risk", "var", "tracking error", "beta", "volatility", "duration", "dv01"),
    "budget": ("budget", "obligation", "award", "appropriation"),
    "program": ("program", "treasury", "fund code"),
    "vendor": ("vendor", "uei", "duns", "cage", "sam"),
    "event": ("action date", "award date", "obligation date", "report date"),
}


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _normalize(field_name: str) -> str:
    return field_name.lower().replace("_", " ").replace("-", " ").strip()


def _keyword_match(field_name: str, normalized: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in normalized
    if keyword.startswith("_"):
        return field_name.lower().endswith(keyword)

    tokens = normalized.split()
    return keyword in tokens


def _infer_type(field_name: str) -> str:
    normalized = _normalize(field_name)
    scores = {}
    for inferred_type, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if _keyword_match(field_name, normalized, keyword))
        if score:
            scores[inferred_type] = score
    return max(scores, key=scores.get) if scores else "unknown"


def _infer_domain(field_name: str) -> str:
    normalized = _normalize(field_name)
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for keyword in keywords if _keyword_match(field_name, normalized, keyword))
        if score:
            scores[domain] = score
    return max(scores, key=scores.get) if scores else "unknown"


def _is_supported_concept(field_type: str, field_domain: str, taxonomy: dict) -> bool:
    for metadata in taxonomy.values():
        type_match = field_type == "unknown" or metadata["data_type"] == field_type
        domain_match = field_domain == "unknown" or metadata["domain"] == field_domain
        if type_match and domain_match:
            return True
    return False


def _type_compatible(field_type: str, target_type: str) -> bool:
    if field_type == "unknown" or target_type == "unknown":
        return True
    if field_type == target_type:
        return True
    compatible_groups = (
        {"amount", "percentage", "rate", "metric"},
        {"identifier", "name"},
        {"category", "status"},
    )
    return any(field_type in group and target_type in group for group in compatible_groups)


def _domain_penalty(field_domain: str, target_domain: str) -> float:
    if field_domain == "unknown" or target_domain == "unknown":
        return 0.0
    if field_domain == target_domain:
        return 0.0

    adjacent_domains = {
        frozenset(("portfolio", "performance")),
        frozenset(("portfolio", "position")),
        frozenset(("position", "security")),
        frozenset(("trade", "counterparty")),
        frozenset(("program", "budget")),
    }
    if frozenset((field_domain, target_domain)) in adjacent_domains:
        return 0.08
    return 0.22


def _score_candidate(client_field: str, metadata: dict) -> tuple[float, str]:
    normalized = _normalize(client_field)
    field_type = _infer_type(client_field)
    field_domain = _infer_domain(client_field)

    best_score = _sim(normalized, metadata.get("target_label", ""))
    best_alias = metadata.get("target_label")

    for alias in metadata["aliases"]:
        score = _sim(normalized, alias.lower())
        if score > best_score:
            best_score = score
            best_alias = alias

    if not _type_compatible(field_type, metadata["data_type"]):
        return 0.0, best_alias

    best_score -= _domain_penalty(field_domain, metadata["domain"])

    if field_type != "unknown" and field_type == metadata["data_type"]:
        best_score += 0.07
    if field_domain != "unknown" and field_domain == metadata["domain"]:
        best_score += 0.05

    return max(0.0, min(best_score, 0.99)), best_alias


# ── MAPPING ENGINE ────────────────────────────────────────────────────

def map_field(client_field: str, taxonomy: dict) -> dict:
    best_target, best_score, best_alias = None, 0.0, None
    field_type = _infer_type(client_field)
    field_domain = _infer_domain(client_field)

    if not _is_supported_concept(field_type, field_domain, taxonomy):
        return {
            "client_field": client_field,
            "target_field": None,
            "matched_via": None,
            "confidence": 0.0,
            "status": "no_match",
            "hitl_required": False,
            "semantic_type": field_type,
            "semantic_domain": field_domain,
            "reason": "unsupported_concept",
        }

    for target, metadata in taxonomy.items():
        candidate = dict(metadata)
        candidate["target_label"] = target.replace("_", " ")
        score, alias = _score_candidate(client_field, candidate)
        if score > best_score:
            best_score, best_target, best_alias = score, target, alias

    from core.completeness import AUTO_THRESHOLD, REVIEW_THRESHOLD
    if best_score < 0.30:
        status = "no_match"
    elif best_score >= AUTO_THRESHOLD:
        status = "auto"
    elif best_score >= REVIEW_THRESHOLD:
        status = "review"
    else:
        status = "no_match"

    result = {
        "client_field": client_field,
        "target_field": best_target if status != "no_match" else None,
        "matched_via": best_alias if status != "no_match" else None,
        "confidence": round(best_score, 3),
        "status": status,
        "hitl_required": status == "review",
        "semantic_type": field_type,
        "semantic_domain": field_domain,
    }
    if status == "no_match":
        result["reason"] = "low_confidence_or_semantic_mismatch"
    return result


def run_mapping(fields: list[str], taxonomy: dict) -> dict:
    results = [map_field(field_name, taxonomy) for field_name in fields]
    auto = [result for result in results if result["status"] == "auto"]
    review = [result for result in results if result["status"] == "review"]
    no_match = [result for result in results if result["status"] == "no_match"]
    return {
        "total": len(results),
        "auto": len(auto),
        "review": len(review),
        "no_match": len(no_match),
        "pct_automated": round(len(auto) / max(len(results), 1) * 100, 1),
        "hitl_required": len(review) > 0,
        "mappings": results,
    }
