"""Read a signed management agreement (PDF) into structured fields.

Primary: Claude reads the PDF directly (text and scanned pages) and fills a strict
schema through a forced tool call. Fallback when no API key is set: pypdf text +
simple patterns, clearly marked as "heuristic" so people double-check it.
"""
import base64
import re
from dataclasses import dataclass, field
from datetime import datetime

from django.conf import settings

FIELDS = {
    "owner_name": "Full legal name of the owner, or the agent/company acting for the owner",
    "owner_type": "'owner' if the signer owns the unit, 'agent' if a company or agent signs on the owner's behalf",
    "owner_email": "Owner or agent email address",
    "owner_phone": "Owner or agent phone number",
    "street_number": "Street number of the building, e.g. '270'",
    "street_name": "Street name with suffix, e.g. 'Queens Quay W'",
    "unit": "Unit or suite number, digits and letters only, e.g. '1204' or 'PH2'",
    "city": "City",
    "postal_code": "Postal code",
    "bedrooms": "Number of bedrooms (integer). A studio is 0",
    "bathrooms": "Number of bathrooms (integer, round half baths down)",
    "beds": "Number of beds if stated (integer)",
    "lease_start": "Agreement or lease start date, YYYY-MM-DD",
    "lease_end": "Agreement or lease end date, YYYY-MM-DD",
    "building_name": "Building or condominium corporation name, if stated",
    "management_company": "Building property-management company, if stated",
    "parking": "Parking spot details, if any",
    "locker": "Locker details, if any",
    "special_terms": "Short summary of unusual terms the team should know (max 3 sentences)",
}
INT_FIELDS = {"bedrooms", "bathrooms", "beds"}
DATE_FIELDS = {"lease_start", "lease_end"}

TOOL = {
    "name": "record_agreement",
    "description": "Record the details found in a short-term-rental management agreement.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": {
                    k: ({"type": ["integer", "null"], "description": d} if k in INT_FIELDS else {"type": ["string", "null"], "description": d})
                    for k, d in FIELDS.items()
                },
            },
            "confidence": {
                "type": "object",
                "description": "For each field you filled: high, medium or low.",
                "additionalProperties": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "notes": {"type": "string", "description": "Anything ambiguous, e.g. two different end dates."},
        },
        "required": ["fields", "confidence"],
    },
}

PROMPT = (
    "This is a signed management agreement between a short-term-rental operator and a unit owner in Canada. "
    "Extract the fields. Use null when a field is not in the document; never guess. "
    "Dates must be YYYY-MM-DD. Mark confidence low when the text is unclear or handwritten."
)


@dataclass
class Extraction:
    fields: dict
    confidence: dict = field(default_factory=dict)
    notes: str = ""
    method: str = "claude"  # claude | heuristic
    model: str = ""

    @property
    def missing(self):
        required = ["owner_name", "street_number", "street_name", "unit", "bedrooms", "bathrooms", "lease_start", "lease_end"]
        return [k for k in required if self.fields.get(k) in (None, "")]


def clean(fields: dict) -> dict:
    out = {}
    for k in FIELDS:
        v = fields.get(k)
        if isinstance(v, str):
            v = v.strip() or None
        if k in INT_FIELDS and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = None
        if k in DATE_FIELDS and v:
            v = normalize_date(v)
        if k == "owner_type" and v not in ("owner", "agent"):
            v = "owner" if v is None else ("agent" if "agent" in str(v).lower() or "inc" in str(v).lower() else "owner")
        out[k] = v
    return out


def normalize_date(v):
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(v.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def extract_with_claude(pdf_bytes: bytes, client=None) -> Extraction:
    import anthropic

    cfg = settings.INTEGRATIONS
    client = client or anthropic.Anthropic(api_key=cfg["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=cfg["ANTHROPIC_MODEL"],
        max_tokens=2000,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_agreement"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                 "data": base64.b64encode(pdf_bytes).decode()}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    block = next(b for b in msg.content if getattr(b, "type", "") == "tool_use")
    data = block.input
    return Extraction(fields=clean(data.get("fields", {})), confidence=data.get("confidence", {}),
                      notes=data.get("notes", ""), method="claude", model=cfg["ANTHROPIC_MODEL"])


# ---------- heuristic fallback ----------

def pdf_text(pdf_bytes: bytes) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _find(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def extract_heuristic(pdf_bytes: bytes) -> Extraction:
    t = pdf_text(pdf_bytes)
    f = {
        "owner_name": _find(r"(?:Owner|Landlord)\s*(?:name)?\s*[:\-]\s*([^\n(]+)", t),
        "owner_email": _find(r"([\w.+-]+@[\w-]+\.[\w.]+)", t),
        "owner_phone": _find(r"(?:Phone|Tel)\s*[:\-]\s*([+\d ()\-]{7,})", t),
        "unit": _find(r"(?:Unit|Suite)\s*(?:#|No\.?)?\s*([A-Z]{0,2}\d+[A-Z]?)", t),
        "postal_code": _find(r"\b([A-Z]\d[A-Z]\s?\d[A-Z]\d)\b", t, 0),
        "bedrooms": _find(r"(\d+)\s*(?:bedrooms?|bed\b|BR\b)", t),
        "bathrooms": _find(r"(\d+)\s*(?:bathrooms?|bath\b|BA\b)", t),
        "beds": _find(r"(?:Beds?)\s*[:\-]\s*(\d+)", t),
        "lease_start": _find(r"(?:Start|Commencement)\s*date\s*[:\-]\s*([A-Za-z0-9 ,/\-]+)", t),
        "lease_end": _find(r"(?:End|Expiry|Termination)\s*date\s*[:\-]\s*([A-Za-z0-9 ,/\-]+)", t),
        "management_company": _find(r"(?:Property management|Management company)\s*[:\-]\s*([^\n]+)", t),
        "parking": _find(r"Parking\s*[:\-]\s*([^\n]+)", t),
        "locker": _find(r"Locker\s*[:\-]\s*([^\n]+)", t),
        "building_name": _find(r"(?:Building|Condominium)\s*(?:name)?\s*[:\-]\s*([^\n]+)", t),
    }
    addr = re.search(r"(\d{1,5})\s+([A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,3}?\s+(?:St|Ave|Rd|Blvd|Dr|Quay|Way|Cres|Ct|Lane|Ln|Pl|Terrace)\.?(?:\s+[NSEW]\b)?)", t)
    if addr:
        f["street_number"], f["street_name"] = addr.group(1), addr.group(2).strip()
    f["city"] = "Toronto" if re.search(r"\bToronto\b", t) else None
    owner = f.get("owner_name") or ""
    f["owner_type"] = "agent" if re.search(r"\b(Inc|Ltd|Realty|Holdings|Corp|Management)\b", owner) else "owner"
    fields = clean(f)
    conf = {k: "low" for k, v in fields.items() if v not in (None, "")}
    return Extraction(fields=fields, confidence=conf, method="heuristic",
                      notes="Read without AI (no ANTHROPIC_API_KEY). Check every field.")


def extract(pdf_bytes: bytes) -> Extraction:
    if settings.INTEGRATIONS["ANTHROPIC_API_KEY"]:
        return extract_with_claude(pdf_bytes)
    return extract_heuristic(pdf_bytes)
