"""Price and stock checking.

Phase 1 ships a deterministic simulated checker so the full flow can be built,
tested and demoed. Real checkers plug in behind the same interface:

    class AmazonPAAPIChecker(PriceChecker):   # Amazon Product Advertising API (needs Associates account)
    class BrowserChecker(PriceChecker):        # Playwright, run only when the client starts it

Pick one with the PRICE_CHECKER setting.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
import hashlib

from django.conf import settings


@dataclass
class PriceResult:
    price: Decimal | None
    in_stock: bool | None
    note: str = ""  # set when the price couldn't be checked; the typical price is used instead

    @property
    def checked(self):
        return self.price is not None


class PriceChecker:
    def check(self, *, name: str, item_type: str, store_code: str, typical_price: Decimal, product_url: str = "") -> PriceResult:
        raise NotImplementedError


class SimulatedPriceChecker(PriceChecker):
    """Repeatable fake results: prices drift ±8% from typical, a few item types are flagged."""

    # exact product name -> (price multiplier or None, in_stock)
    FLAGGED = {
        "12-cup coffee maker": (None, False),
        "duvet insert, queen": (Decimal("1.33"), True),
        "shower dispenser, 3 chamber": (None, False),
        "sofa, 3-seat": (Decimal("1.31"), True),
    }

    def check(self, *, name, item_type, store_code, typical_price, product_url=""):
        typical = Decimal(typical_price)
        flagged = self.FLAGGED.get(name.strip().lower())
        if flagged:
            mult, stock = flagged
            price = typical * mult if mult else typical
            return PriceResult(price.quantize(Decimal("0.01"), ROUND_HALF_UP), stock)
        h = int(hashlib.sha1(f"{store_code}:{name}".encode()).hexdigest()[:6], 16)
        drift = Decimal((h % 17) - 8) / Decimal(100)  # -8% .. +8%
        return PriceResult((typical * (1 + drift)).quantize(Decimal("0.01"), ROUND_HALF_UP), True)


class WebPriceChecker(PriceChecker):
    """Reads price and stock from the product's own page (schema.org JSON-LD, then meta tags).

    Runs only when someone clicks "Run price and stock check", one request per item, with a
    timeout. Stores that block automated requests return "couldn't check" and the line keeps
    its typical price, so a person can verify it by hand.
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36 OnboardingPriceCheck/1.0",
        "Accept-Language": "en-CA,en;q=0.9",
    }

    def __init__(self, session=None, timeout=12):
        import requests
        self.http = session or requests.Session()
        self.timeout = timeout

    def check(self, *, name, item_type, store_code, typical_price, product_url=""):
        if not product_url:
            return PriceResult(None, None, "No product link in the master list")
        try:
            r = self.http.get(product_url, headers=self.HEADERS, timeout=self.timeout)
        except Exception as e:  # noqa: BLE001 - network errors become a soft "couldn't check"
            return PriceResult(None, None, f"Couldn't reach the store ({type(e).__name__})")
        if r.status_code in (403, 429, 503):
            return PriceResult(None, None, "The store blocked the automated check. Verify by hand.")
        if not r.ok:
            return PriceResult(None, None, f"Product page returned {r.status_code}. Check the link.")
        price, stock = parse_product_page(r.text)
        if price is None:
            return PriceResult(None, stock, "Price not found on the page. Verify by hand.")
        return PriceResult(price, True if stock is None else stock)


def _to_decimal(v):
    import re
    if v is None:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(",", "")).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        return None


def _stock_from(text):
    t = str(text or "").lower()
    if any(k in t for k in ("outofstock", "out of stock", "soldout", "sold out", "discontinued")):
        return False
    if any(k in t for k in ("instock", "in stock", "limitedavailability", "onlineonly", "preorder")):
        return True
    return None


def parse_product_page(html):
    """Return (price, in_stock) from structured data on a product page; either may be None."""
    import json
    import re

    def products(node):
        if isinstance(node, list):
            for n in node:
                yield from products(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" in types or "ProductGroup" in types:
                yield node
            for k in ("@graph", "mainEntity", "itemListElement"):
                if k in node:
                    yield from products(node[k])

    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for prod in products(data):
            offers = prod.get("offers")
            if not offers and isinstance(prod.get("hasVariant"), list) and prod["hasVariant"]:
                offers = prod["hasVariant"][0].get("offers")
            offers = offers or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if offers.get("@type") == "AggregateOffer" and not offers.get("price"):
                price = _to_decimal(offers.get("lowPrice"))
            else:
                price = _to_decimal(offers.get("price") or (offers.get("priceSpecification") or {}).get("price"))
            if price is not None:
                return price, _stock_from(offers.get("availability"))

    def meta(prop):
        m = re.search(r'<meta[^>]+(?:property|name|itemprop)=["\']' + re.escape(prop) + r'["\'][^>]*content=["\']([^"\']+)', html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']' + re.escape(prop), html, re.I)
        return m.group(1) if m else None

    price = _to_decimal(meta("product:price:amount") or meta("og:price:amount") or meta("price"))
    stock = _stock_from(meta("product:availability") or meta("og:availability") or meta("availability"))
    return price, stock


CHECKERS = {"simulated": SimulatedPriceChecker, "web": WebPriceChecker}


def get_checker() -> PriceChecker:
    return CHECKERS[settings.PROCUREMENT["PRICE_CHECKER"]]()


def flag_for(result: PriceResult, typical_price: Decimal) -> str:
    if result.in_stock is False:
        return "Out of stock"
    if result.price is None:
        return ""
        return "Out of stock"
    threshold = Decimal(str(settings.PROCUREMENT["OVER_PRICE_THRESHOLD"]))
    typical = Decimal(typical_price)
    if typical > 0 and (result.price - typical) / typical > threshold:
        pct = round((result.price - typical) / typical * 100)
        return f"Price {pct}% above typical"
    return ""
