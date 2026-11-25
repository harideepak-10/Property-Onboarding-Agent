"""Guesty Open API client (https://open-api-docs.guesty.com).

- Auth: OAuth2 client credentials, token valid 24h, max 5 token requests per 24h per client,
  so the token is cached in the database and reused.
- Create listing: POST /v1/listings (created active; isListed=false keeps it off the marketplaces
  until go-live).
- Photos: POST /v1/properties-api/property-photos/property-photos/{id} with [{url, caption}].
  Guesty downloads each URL, so photos must be publicly reachable (PUBLIC_BASE_URL).
- Replace the whole set on a re-shoot: PUT /v1/listings/{id} with "pictures".

Verify request bodies against a Guesty sandbox/test account before go-live;
Guesty's reference pages are the source of truth.

Without GUESTY_CLIENT_ID/SECRET the client runs in dry-run mode.
"""
import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .models import GuestyToken

log = logging.getLogger(__name__)


class GuestyError(Exception):
    pass


class Result(dict):
    @property
    def dry_run(self):
        return self.get("dry_run", False)


class Guesty:
    def __init__(self, cfg=None, session=None):
        self.cfg = cfg or settings.LISTINGS
        self.http = session or requests.Session()

    @property
    def live(self):
        return bool(self.cfg.get("GUESTY_CLIENT_ID") and self.cfg.get("GUESTY_CLIENT_SECRET"))

    # ----- auth -----
    def token(self):
        cached = GuestyToken.objects.filter(expires_at__gt=timezone.now() + timedelta(minutes=5)).first()
        if cached:
            return cached.access_token
        r = self.http.post(f"{self.cfg['GUESTY_BASE_URL']}/oauth2/token", data={
            "grant_type": "client_credentials", "scope": "open-api",
            "client_id": self.cfg["GUESTY_CLIENT_ID"], "client_secret": self.cfg["GUESTY_CLIENT_SECRET"],
        }, headers={"Accept": "application/json"}, timeout=30)
        if r.status_code == 429:
            raise GuestyError("Guesty token limit reached (5 per 24 hours). Try again later.")
        if not r.ok:
            raise GuestyError(f"Guesty login failed ({r.status_code}): {r.text[:200]}")
        data = r.json()
        GuestyToken.objects.all().delete()
        GuestyToken.objects.create(access_token=data["access_token"],
                                   expires_at=timezone.now() + timedelta(seconds=int(data.get("expires_in", 86400))))
        return data["access_token"]

    def _call(self, method, path, json=None):
        r = self.http.request(method, f"{self.cfg['GUESTY_BASE_URL']}/v1{path}", json=json, timeout=60,
                              headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/json"})
        if not r.ok:
            raise GuestyError(f"Guesty {method} {path} failed ({r.status_code}): {r.text[:300]}")
        return r.json() if r.content else {}

    # ----- listings -----
    def create_listing(self, payload):
        if not self.live:
            return Result(_id=f"dryrun-{uuid.uuid4().hex[:12]}", dry_run=True)
        return Result(self._call("POST", "/listings", payload))

    def add_photos(self, listing_id, photos):
        """photos: [{"url", "caption"}]"""
        if not self.live or listing_id.startswith("dryrun-"):
            return Result(count=len(photos), dry_run=True)
        self._call("POST", f"/properties-api/property-photos/property-photos/{listing_id}", photos)
        return Result(count=len(photos))

    def set_listed(self, listing_id, listed: bool):
        """PUT /v1/listings/{id} {"isListed": ...}: lists on (or hides from) the connected channels."""
        if not self.live or listing_id.startswith("dryrun-"):
            return Result(isListed=listed, dry_run=True)
        return Result(self._call("PUT", f"/listings/{listing_id}", {"isListed": listed}))

    def replace_photos(self, listing_id, photos):
        if not self.live or listing_id.startswith("dryrun-"):
            return Result(count=len(photos), dry_run=True)
        pictures = [{"original": p["url"], "thumbnail": p["url"], "caption": p.get("caption", "")} for p in photos]
        self._call("PUT", f"/listings/{listing_id}", {"pictures": pictures})
        return Result(count=len(photos))


def listing_payload(prop, profile):
    cfg = settings.LISTINGS
    return {
        "nickname": prop.nickname,
        "title": profile.effective_title(),
        "type": "SINGLE",
        "roomType": "Entire home/apartment",
        "propertyType": profile.property_type,
        "accommodates": profile.effective_accommodates(),
        "bedrooms": prop.bedrooms,
        "bathrooms": prop.bathrooms,
        "beds": prop.beds,
        "timezone": cfg["TIMEZONE"],
        "isListed": False,  # stays off Airbnb/Booking.com until the go-live step
        "address": {
            "full": f"{prop.street_number} {prop.street_name}, Unit {prop.unit}, {prop.city}, ON {prop.postal_code}".strip(),
            "street": f"{prop.street_number} {prop.street_name}",
            "apartment": prop.unit,
            "city": prop.city,
            "state": "ON",
            "zipcode": prop.postal_code,
            "country": "Canada",
        },
        "prices": {"basePrice": profile.base_price or cfg["DEFAULT_BASE_PRICE"], "currency": cfg["CURRENCY"],
                   **({"cleaningFee": profile.cleaning_fee} if profile.cleaning_fee else {})},
        "amenities": profile.amenities,
    }
