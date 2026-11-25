"""Email drafts written by agents, and sending them after a person approves."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from onboarding.engine import complete_by_title
from properties.services import log

from .integrations.google_workspace import GoogleWorkspace
from .models import EmailDraft


def fmt(d):
    """'January 5, 2027' on every OS (strftime %-d doesn't work on Windows)."""
    if isinstance(d, str):
        from datetime import date
        d = date.fromisoformat(d)
    return f"{d:%B} {d.day}, {d.year}"


def _lease(prop):
    if prop.lease_start and prop.lease_end:
        return f"{fmt(prop.lease_start)} to {fmt(prop.lease_end)}"
    return "the dates in the attached agreement"


def building_registration(prop) -> EmailDraft:
    b = prop.building
    extras = [x for x in [f"Parking: {prop.parking}" if prop.parking else "", f"Locker: {prop.locker}" if prop.locker else ""] if x]
    body = f"""Hello{f' {b.management_company}' if b and b.management_company else ''} team,

We manage unit {prop.unit} at {prop.street_number} {prop.street_name} on behalf of the owner, {prop.owner_name}. Please find the signed agreement attached to register the unit with the building.

Unit: {prop.unit}
Term: {_lease(prop)}
Owner: {prop.owner_name}{f' ({prop.owner_email})' if prop.owner_email else ''}
{chr(10).join(extras) + chr(10) if extras else ''}
Could you please let us know what is needed to:
- register the unit and our contact details with the management office
- set up keys and fobs (quantity and any fees)
- register parking{', if applicable' if not prop.parking else ''}
- book the elevator for furniture delivery and move-in

If there are forms to fill in, please send them over and we'll return them promptly.

Thank you,
Operations team
{settings.AGENTS['OPS_EMAIL']}
"""
    warning = ""
    if not b:
        warning = "This building isn't in the Buildings list yet. Add it so the agent knows who to email."
    elif not b.management_email:
        warning = f"No management email on file for {b}. Add one before sending."
    return EmailDraft.objects.create(
        property=prop, kind=EmailDraft.Kind.BUILDING_REGISTRATION, to=(b.management_email if b else ""),
        subject=f"Unit {prop.unit} registration – {prop.street_number} {prop.street_name}",
        body=body, attach_agreement=True, warning=warning, created_by_agent="Intake agent")


def building_followup(prop, original: EmailDraft, open_items) -> EmailDraft:
    items = "\n".join(f"- {t}" for t in open_items)
    body = f"""Hello,

Following up on our email from {fmt(timezone.localtime(original.sent_at).date())} about unit {prop.unit} at {prop.street_number} {prop.street_name}. We are still waiting on:

{items}

Could you let us know the next steps or send any forms we need to complete?

Thank you,
Operations team
{settings.AGENTS['OPS_EMAIL']}
"""
    return EmailDraft.objects.create(
        property=prop, kind=EmailDraft.Kind.BUILDING_FOLLOWUP, to=original.to, cc=original.cc,
        subject=f"Following up: {original.subject}", body=body, created_by_agent="Intake agent")


def owner_documents(prop, missing) -> EmailDraft:
    items = "\n".join(f"- {m}" for m in missing)
    body = f"""Hi {prop.owner_name.split()[0] if prop.owner_name else ''},

To register unit {prop.unit} at {prop.street_number} {prop.street_name} for its short-term rental licence, we still need:

{items}

You can reply to this email with the documents attached. Thank you!

Operations team
{settings.AGENTS['OPS_EMAIL']}
"""
    return EmailDraft.objects.create(
        property=prop, kind=EmailDraft.Kind.OWNER_DOCUMENTS, to=prop.owner_email,
        subject=f"Documents needed for unit {prop.unit} licence",
        body=body, warning="" if prop.owner_email else "No owner email on file.", created_by_agent="Compliance agent")


def licence_renewal(prop, licence, days_left) -> EmailDraft:
    body = f"""Licence renewal reminder

Property: {prop.nickname} ({prop.address})
Licence: {licence.number or 'number not recorded'}
Expires: {fmt(licence.expires_on)} ({days_left} days from today)

Start the renewal with the City so the listing doesn't have to be paused. The listing must keep showing a valid licence number.
"""
    return EmailDraft.objects.create(
        property=prop, kind=EmailDraft.Kind.LICENCE_RENEWAL, to=settings.AGENTS["OPS_EMAIL"],
        subject=f"[{days_left} days] STR licence renewal for {prop.nickname}", body=body,
        created_by_agent="Compliance agent")


def licence_expired(prop, licence) -> EmailDraft:
    body = f"""URGENT: STR licence expired while the listing is live

Property: {prop.nickname} ({prop.address})
Licence: {licence.number or 'number not recorded'}
Expired: {fmt(licence.expires_on)}

The listing is still listed in Guesty. Unlist it from the property's Go live tab until the licence is renewed.
"""
    return EmailDraft.objects.create(
        property=prop, kind=EmailDraft.Kind.LICENCE_RENEWAL, to=settings.AGENTS["OPS_EMAIL"],
        subject=f"[URGENT] Licence expired: {prop.nickname} is still listed", body=body, created_by_agent="Compliance agent")


# What sending each kind of email completes on the checklist
ON_SENT = {
    EmailDraft.Kind.BUILDING_REGISTRATION: (2, ["Lease sent to building management"]),
    EmailDraft.Kind.ANGEL_HOST: (10, ["Angel Host emailed: ready to optimize"]),
}


@transaction.atomic
def send(draft: EmailDraft, user=None, google=None) -> EmailDraft:
    if draft.status != EmailDraft.Status.DRAFT:
        raise ValidationError("This email was already sent or discarded.")
    if not draft.to.strip():
        raise ValidationError("Add a recipient before sending.")
    google = google or GoogleWorkspace()
    attachments = []
    if draft.attach_agreement:
        doc = draft.property.agreements.first()
        if doc:
            with doc.file.open("rb") as f:
                attachments.append((doc.original_name, f.read(), "application/pdf"))
    res = google.send_email(draft.to, draft.subject, draft.body, cc=draft.cc or None, attachments=attachments)
    draft.status, draft.sent_at, draft.sent_by = EmailDraft.Status.SENT, timezone.now(), user
    draft.sent_dry_run, draft.message_id = res.dry_run, res.get("id", "")
    draft.save()
    who = (user.get_full_name() or user.get_username()) if user else "Team"
    log(draft.property, f"{'Dry run: would have sent' if res.dry_run else 'Sent'} email “{draft.subject}” to {draft.to}", actor=who, user=user)
    if draft.kind in ON_SENT:
        step, titles = ON_SENT[draft.kind]
        try:
            complete_by_title(draft.property, step, titles, actor=who, user=user,
                              proof_note=f"Email sent {draft.sent_at:%Y-%m-%d} to {draft.to}")
        except ValidationError:
            pass  # step locked: the email still counts, the task can be ticked later
    return draft
