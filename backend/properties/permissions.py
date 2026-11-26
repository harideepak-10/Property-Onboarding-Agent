"""Role-based access. Every signed-in user can read; writes depend on the role.

admin        everything, including users and the master list
manager      everything except user management and approving orders
coordinator  day-to-day work; can't approve orders, send emails, approve go-live or unlist, or edit the master list
viewer       read-only

Superusers without a profile are treated as admins; other users without a profile as coordinators.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

ROLES = ["admin", "manager", "coordinator", "viewer"]

PERMISSIONS = {
    "approve_orders": {"admin"},                 # client decision: only admins approve spending
    "send_emails": {"admin", "manager"},
    "approve_go_live": {"admin", "manager"},
    "edit_master_list": {"admin", "manager"},
    "manage_users": {"admin"},
    "edit": {"admin", "manager", "coordinator"},
}

# (path fragment, permission). The first match wins; anything else that writes needs "edit".
RULES = [
    ("/auth/users", "manage_users"),
    ("/approve", "approve_orders"),          # orders/{id}/approve
    ("/go-live/approve", "approve_go_live"),
    ("/go-live/unlist", "approve_go_live"),
    ("/send", "send_emails"),                # emails/{id}/send
    ("/master-items", "edit_master_list"),
]


def role_of(user):
    if not user or not user.is_authenticated:
        return None
    prof = getattr(user, "profile", None)
    try:
        if prof is not None:
            return prof.role
    except Exception:
        pass
    return "admin" if user.is_superuser else "coordinator"


def can(user, perm):
    return role_of(user) in PERMISSIONS.get(perm, set())


def permissions_for(user):
    return sorted(p for p in PERMISSIONS if can(user, p))


def required_permission(path):
    for frag, perm in RULES:
        if frag in path:
            # go-live/approve must not be caught by the generic order /approve rule
            if frag == "/approve" and "/go-live/approve" in path:
                return "approve_go_live"
            return perm
    return "edit"


class RolePermission(BasePermission):
    message = "Your role doesn't allow this action."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS or not request.user or not request.user.is_authenticated:
            return True  # IsAuthenticated handles anonymous users
        if request.path.rstrip("/").endswith("/auth/login"):
            return True
        return can(request.user, required_permission(request.path))
