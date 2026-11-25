"""Google Drive, Sheets, Gmail and Admin SDK, behind one client with a dry-run mode.

Live mode needs a service account JSON with domain-wide delegation for these scopes,
granted in the Workspace admin console:
    https://www.googleapis.com/auth/drive
    https://www.googleapis.com/auth/spreadsheets
    https://www.googleapis.com/auth/gmail.send
    https://www.googleapis.com/auth/admin.directory.user
Each feature is live only when its own setting is filled in; otherwise it dry-runs
and returns placeholder IDs so the rest of the workflow can continue.
"""
import base64
import logging
import secrets
import uuid
from email.message import EmailMessage

from django.conf import settings

log = logging.getLogger(__name__)

SCOPES = {
    "drive": ["https://www.googleapis.com/auth/drive"],
    "sheets": ["https://www.googleapis.com/auth/spreadsheets"],
    "gmail": ["https://www.googleapis.com/auth/gmail.send"],
    "admin": ["https://www.googleapis.com/auth/admin.directory.user"],
}


class Result(dict):
    """dict with .dry_run so callers can say 'would have…' in the activity log."""

    @property
    def dry_run(self):
        return self.get("dry_run", False)


def _fake_id(prefix):
    return f"dryrun-{prefix}-{uuid.uuid4().hex[:10]}"


class GoogleWorkspace:
    def __init__(self, cfg=None):
        self.cfg = cfg or settings.INTEGRATIONS

    # ----- mode -----
    @property
    def has_credentials(self):
        return bool(self.cfg.get("GOOGLE_SERVICE_ACCOUNT_FILE"))

    def live(self, feature):
        needs = {
            "drive": ["GOOGLE_DRIVE_PARENT_FOLDER_ID"],
            "sheets": ["GOOGLE_TRACKER_SHEET_ID"],
            "gmail": ["GOOGLE_SENDER_EMAIL"],
            "admin": ["GOOGLE_DELEGATED_ADMIN"],
        }[feature]
        return self.has_credentials and all(self.cfg.get(k) for k in needs)

    def status(self):
        return {f: ("live" if self.live(f) else "dry_run") for f in ("drive", "sheets", "gmail", "admin")}

    def _service(self, api, version, feature, subject=None):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            self.cfg["GOOGLE_SERVICE_ACCOUNT_FILE"], scopes=SCOPES[feature])
        if subject:
            creds = creds.with_subject(subject)
        return build(api, version, credentials=creds, cache_discovery=False)

    # ----- Drive -----
    def create_folder(self, name, parent_id=None):
        parent_id = parent_id or self.cfg.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
        if not self.live("drive"):
            fid = _fake_id("folder")
            return Result(id=fid, url=f"https://drive.google.com/drive/folders/{fid}", dry_run=True)
        svc = self._service("drive", "v3", "drive")
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
        f = svc.files().create(body=meta, fields="id, webViewLink", supportsAllDrives=True).execute()
        return Result(id=f["id"], url=f["webViewLink"])

    def upload_file(self, folder_id, path, name, mime="application/pdf"):
        if not self.live("drive") or folder_id.startswith("dryrun-"):
            fid = _fake_id("file")
            return Result(id=fid, url=f"https://drive.google.com/file/d/{fid}/view", dry_run=True)
        from googleapiclient.http import MediaFileUpload

        svc = self._service("drive", "v3", "drive")
        f = svc.files().create(body={"name": name, "parents": [folder_id]}, media_body=MediaFileUpload(path, mimetype=mime),
                               fields="id, webViewLink", supportsAllDrives=True).execute()
        return Result(id=f["id"], url=f["webViewLink"])

    @staticmethod
    def folder_id_from_url(url):
        import re
        m = re.search(r"/folders/([\w-]+)", url or "") or re.search(r"[?&]id=([\w-]+)", url or "")
        return m.group(1) if m else None

    def list_images(self, folder_id):
        """Image files in a Drive folder (the photographer's shared link): [{id, name, mimeType}]."""
        if not self.has_credentials:
            return Result(files=[], dry_run=True)
        svc = self._service("drive", "v3", "drive")
        files, token = [], None
        while True:
            r = svc.files().list(q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false",
                                 fields="nextPageToken, files(id, name, mimeType)", orderBy="name", pageSize=200,
                                 pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            files += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                return Result(files=files)

    def download(self, file_id):
        import io
        from googleapiclient.http import MediaIoBaseDownload

        svc = self._service("drive", "v3", "drive")
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id, supportsAllDrives=True))
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()

    # ----- Sheets -----
    def append_row(self, values, sheet_id=None, rng=None):
        sheet_id = sheet_id or self.cfg.get("GOOGLE_TRACKER_SHEET_ID")
        rng = rng or self.cfg.get("GOOGLE_TRACKER_RANGE")
        if not self.live("sheets"):
            return Result(updated_range=f"{rng} (dry run)", dry_run=True)
        svc = self._service("sheets", "v4", "sheets")
        r = svc.spreadsheets().values().append(
            spreadsheetId=sheet_id, range=rng, valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS", body={"values": [values]}).execute()
        return Result(updated_range=r.get("updates", {}).get("updatedRange", rng))

    # ----- Gmail -----
    def send_email(self, to, subject, body, cc=None, reply_to=None, attachments=()):
        """attachments: iterable of (filename, bytes, mime)."""
        sender = self.cfg.get("GOOGLE_SENDER_EMAIL") or settings.AGENTS["OPS_EMAIL"]
        if not self.live("gmail"):
            return Result(id=_fake_id("msg"), sender=sender, dry_run=True)
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = to, sender, subject
        if cc:
            msg["Cc"] = cc
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        for filename, data, mime in attachments:
            maintype, subtype = mime.split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        svc = self._service("gmail", "v1", "gmail", subject=sender)
        r = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return Result(id=r["id"], sender=sender)

    # ----- Admin SDK -----
    def create_user(self, primary_email, given_name, family_name):
        """Create a Workspace mailbox. The temporary password is never stored; it must be reset in the admin console."""
        if not self.live("admin"):
            return Result(email=primary_email, dry_run=True)
        svc = self._service("admin", "directory_v1", "admin", subject=self.cfg["GOOGLE_DELEGATED_ADMIN"])
        try:
            svc.users().get(userKey=primary_email).execute()
            return Result(email=primary_email, existed=True)
        except Exception:  # noqa: BLE001 - not found is the normal path
            pass
        svc.users().insert(body={
            "primaryEmail": primary_email,
            "name": {"givenName": given_name, "familyName": family_name},
            "password": secrets.token_urlsafe(24),
            "changePasswordAtNextLogin": True,
        }).execute()
        return Result(email=primary_email, created=True)


def anthropic_status():
    return "live" if settings.INTEGRATIONS["ANTHROPIC_API_KEY"] else "heuristic"
