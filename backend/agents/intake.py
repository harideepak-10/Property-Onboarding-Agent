"""Intake agent: signed agreement → property, Drive folder, tracker row, building email.

Every action is written to an AgentRun trace so the team (and the client) can see
exactly what the agent did, and what it only would have done in dry-run mode.
"""
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from onboarding.engine import complete_by_title
from properties.services import create_property, log

from . import emails
from .integrations import extraction
from .integrations.google_workspace import GoogleWorkspace
from .models import AgentRun, AgreementDocument, Building

AGENT = "Intake agent"


def tick(prop, step, titles, user=None, note=""):
    """Tick checklist tasks; returns False (instead of failing the run) if the step is still locked."""
    try:
        complete_by_title(prop, step, titles, actor=AGENT, user=user, proof_note=note)
        return True
    except ValidationError:
        return False
PROPERTY_FIELDS = ["owner_name", "owner_type", "owner_email", "owner_phone", "street_number", "street_name", "unit",
                   "city", "postal_code", "bedrooms", "bathrooms", "beds", "lease_start", "lease_end", "nickname"]


def read_agreement(doc: AgreementDocument) -> AgreementDocument:
    """Extract fields from the uploaded PDF. Never raises: failures are stored on the document."""
    try:
        with doc.file.open("rb") as f:
            result = extraction.extract(f.read())
        doc.extracted, doc.confidence, doc.notes = result.fields, result.confidence, result.notes
        doc.method, doc.model = result.method, result.model
        doc.status, doc.error = AgreementDocument.Status.EXTRACTED, ""
    except Exception as e:  # noqa: BLE001 - surface any reader/API failure to the user
        doc.status, doc.error = AgreementDocument.Status.FAILED, f"{type(e).__name__}: {e}"
    doc.save()
    return doc


def _apply_fields(fields: dict) -> dict:
    data = {k: fields.get(k) for k in PROPERTY_FIELDS if fields.get(k) not in (None, "")}
    if not data.get("beds"):
        data["beds"] = max(1, int(data.get("bedrooms") or 1))
    data.setdefault("owner_type", "owner")
    for k in ("street_number", "street_name", "unit", "owner_name"):
        if not data.get(k):
            raise ValidationError(f"{k.replace('_', ' ').capitalize()} is required.")
    return data


@transaction.atomic
def create_from_agreement(doc: AgreementDocument, confirmed_fields: dict, user=None):
    """Create the property from fields a person has reviewed, then run the intake steps."""
    if doc.status == AgreementDocument.Status.APPLIED:
        raise ValidationError("A property was already created from this agreement.")
    fields = {**doc.extracted, **(confirmed_fields or {})}
    data = _apply_fields(fields)
    prop = create_property(data, user=user)
    prop.refresh_from_db()  # dates as date objects, not the strings we passed in
    prop.parking = fields.get("parking") or ""
    prop.locker = fields.get("locker") or ""
    prop.special_terms = fields.get("special_terms") or ""
    prop.save(update_fields=["parking", "locker", "special_terms"])
    building = Building.match(prop.street_number, prop.street_name)
    if not building and (fields.get("building_name") or fields.get("management_company")):
        building = Building.objects.create(street_number=prop.street_number, street_name=prop.street_name,
                                           name=fields.get("building_name") or "",
                                           management_company=fields.get("management_company") or "")
    if building:
        prop.building = building
        prop.save(update_fields=["building"])
    doc.property, doc.status, doc.extracted = prop, AgreementDocument.Status.APPLIED, fields
    doc.save()
    run = run_intake(prop, user=user)
    return prop, run


def run_intake(prop, user=None, google=None, run=None) -> AgentRun:
    google = google or GoogleWorkspace()
    run = run or AgentRun.objects.create(agent=AgentRun.Agent.INTAKE, property=prop, started_by=user)
    warnings = 0
    try:
        doc = prop.agreements.first()

        # 1. Agreement received
        if doc:
            tick(prop, 1, ["Owner signed agreement"], user)
            run.add("Read the signed agreement", detail=f"{doc.original_name} · read with {doc.method or 'manual entry'}")
        else:
            run.add("No agreement PDF on file", "warn", "Upload the signed agreement to complete step 1.")
            warnings += 1

        # 2. Drive folder + subfolders
        if not prop.drive_folder_id:
            folder = google.create_folder(f"{prop.nickname} – {prop.address}")
            prop.drive_folder_id, prop.drive_folder_url = folder["id"], folder["url"]
            prop.save(update_fields=["drive_folder_id", "drive_folder_url"])
            subs = {name: google.create_folder(name, parent_id=folder["id"]) for name in settings.AGENTS["DRIVE_SUBFOLDERS"]}
            run.add("Created the unit's Google Drive folder", detail=f"{prop.nickname} with {len(subs)} subfolders", dry_run=folder.dry_run)
        else:
            subs = {}
            run.add("Drive folder already exists", "skip", prop.drive_folder_url)

        # 3. Upload the agreement into Agreement/
        if doc and not doc.drive_file_url:
            target = subs.get("Agreement", {}).get("id") or prop.drive_folder_id
            up = google.upload_file(target, doc.file.path, doc.original_name, mimetypes.guess_type(doc.original_name)[0] or "application/pdf")
            doc.drive_file_url = up["url"]
            doc.save(update_fields=["drive_file_url"])
            tick(prop, 1, ["Signed PDF received"], user, "Uploaded to the unit's Drive folder")
            tick(prop, 2, ["Agreement saved to unit Drive folder"], user, f"Drive: {up['url']}")
            run.add("Saved the agreement in Drive › Agreement", detail=doc.original_name, dry_run=up.dry_run)

        # 4. Portfolio tracker row
        lic = prop.licence
        row = [prop.nickname, prop.address, prop.owner_name, prop.get_owner_type_display(),
               str(prop.lease_start or ""), str(prop.lease_end or ""), lic.get_status_display(), lic.number,
               str(lic.expires_on or ""), prop.drive_folder_url]
        res = google.append_row(row)
        if tick(prop, 2, ["Added to portfolio tracker"], user):
            run.add("Added the unit to the portfolio tracker", detail=res["updated_range"], dry_run=res.dry_run)
        else:
            warnings += 1
            run.add("Added the unit to the portfolio tracker", "warn", "Row added, but step 2 is locked until step 1 is complete.", dry_run=res.dry_run)

        # 5. Building registration email (draft for approval)
        if not prop.email_drafts.filter(kind="building_registration").exists():
            draft = emails.building_registration(prop)
            if draft.warning:
                warnings += 1
                run.add("Drafted the building registration email", "warn", draft.warning)
            else:
                run.add("Drafted the building registration email", detail=f"To {draft.to} · waiting for your approval")

        log(prop, "Intake agent finished: Drive folder, tracker row and building email draft", actor=AGENT, user=user)
        run.status = AgentRun.Status.PARTIAL if warnings else AgentRun.Status.SUCCEEDED
    except Exception as e:  # noqa: BLE001
        run.add("Stopped because of an error", "error", f"{type(e).__name__}: {e}")
        run.status, run.error = AgentRun.Status.FAILED, str(e)
    run.finished_at = timezone.now()
    run.save()
    return run
