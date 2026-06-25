"""Permission strings, role presets, and the role -> UI capability matrix.

The capability matrix (``ROLE_MENU_MATRIX`` / ``ROLE_DATA_SCOPE``) is the
single source of truth consumed by the ``/auth/me/capabilities`` endpoint
so the frontend can hide menus, action buttons and out-of-scope data
without re-deriving role logic in TypeScript.
"""

# ---- Permission strings ----
WILDCARD = "*"

# Users / roles
USERS_READ = "users:read"
USERS_WRITE = "users:write"
ROLES_READ = "roles:read"
ROLES_WRITE = "roles:write"

# Masters
MASTERS_READ = "masters:read"
MASTERS_WRITE = "masters:write"

# Cases — placeholders, filled out in later phases
CASES_CREATE = "cases:create"
CASES_READ = "cases:read"
CASES_APPROVE_SALES_MGR = "cases:approve:sales_mgr"
CASES_APPROVE_DIV_MGR = "cases:approve:div_mgr"
CASES_APPROVE_AUDIT = "cases:approve:audit"
CASES_APPROVE_FM = "cases:approve:fm"
CASES_APPROVE_ED = "cases:approve:ed"
CASES_APPROVE_FINAL = "cases:approve:final"
CASES_LAWYER_APPROVE = "cases:approve:lawyer"
CASES_FILE = "cases:file"
CASES_SIGNED_FORM = "cases:signed_form"
HEARINGS_WRITE = "hearings:write"
EXPENSES_REQUEST = "expenses:request"
EXPENSES_APPROVE = "expenses:approve"
EXPENSES_PAY = "expenses:pay"

# Phase 41: physical document chain of custody
DOCUMENTS_READ = "documents:read"
DOCUMENTS_TRANSFER = "documents:transfer"

# Admin
ADMIN_SETTINGS = "admin:settings"
ADMIN_BACKUP = "admin:backup"
ADMIN_AUDIT_LOG = "admin:audit_log"
ADMIN_EMAIL_LOG = "admin:email_log"

# ---- Role presets (used by seed) ----
ROLE_PRESETS: dict[str, list[str]] = {
    "Admin": [WILDCARD],
    "Accountant": [
        CASES_CREATE,
        CASES_READ,
        EXPENSES_PAY,
        MASTERS_READ,
        DOCUMENTS_READ,
        DOCUMENTS_TRANSFER,
    ],
    "Sales Manager": [
        CASES_READ,
        CASES_APPROVE_SALES_MGR,
        MASTERS_READ,
        DOCUMENTS_READ,
    ],
    "Division Manager": [
        CASES_READ,
        CASES_APPROVE_DIV_MGR,
        MASTERS_READ,
        DOCUMENTS_READ,
    ],
    "Auditor": [
        CASES_READ,
        CASES_APPROVE_AUDIT,
        ADMIN_AUDIT_LOG,
        MASTERS_READ,
        DOCUMENTS_READ,
    ],
    "Finance Manager": [
        CASES_READ,
        CASES_APPROVE_FM,
        CASES_SIGNED_FORM,
        EXPENSES_APPROVE,
        MASTERS_READ,
        DOCUMENTS_READ,
    ],
    "Executive Director": [
        CASES_READ,
        CASES_APPROVE_ED,
        MASTERS_READ,
        DOCUMENTS_READ,
    ],
    "Chairman / MD": [
        CASES_READ,
        CASES_APPROVE_FINAL,
        MASTERS_READ,
        DOCUMENTS_READ,
    ],
    "Lawyer": [
        CASES_READ,
        CASES_FILE,
        CASES_LAWYER_APPROVE,
        CASES_SIGNED_FORM,
        HEARINGS_WRITE,
        EXPENSES_REQUEST,
        MASTERS_READ,
        DOCUMENTS_READ,
        DOCUMENTS_TRANSFER,
    ],
}


def has_permission(user_perms: list[str], required: str) -> bool:
    if WILDCARD in user_perms:
        return True
    if required in user_perms:
        return True
    # prefix wildcards: "cases:*" grants "cases:create" etc.
    for p in user_perms:
        if p.endswith(":*") and required.startswith(p[:-1]):
            return True
    return False


# ---------------------------------------------------------------------------
# Capability matrix
# ---------------------------------------------------------------------------
#
# Each role maps to:
#   - ``menus``   : sidebar menu IDs the user may see
#   - ``actions`` : action button IDs the user may invoke
#   - ``scope``   : data-scope hints (``own_divisions`` = filter by
#                   user.divisions; ``all`` = no division filter)
#
# Menu IDs match the ``id`` field in the frontend sidebar configuration.
# Action IDs match the ``id`` props on CaseActions / ClosurePanel etc.
# Anything not listed is implicitly hidden.

# Menu IDs (keep in sync with frontend/components/Sidebar.tsx)
MENU_DASHBOARD = "dashboard"
MENU_PROFILE = "profile"
MENU_CASES = "cases"
MENU_APPROVALS = "approvals"
MENU_HEARINGS = "hearings"
MENU_CASH_REQUESTS = "cash_requests"
MENU_REPORTS = "reports"
MENU_SCHEDULED_REPORTS = "scheduled_reports"
MENU_MASTERS_DIVISIONS = "masters.divisions"
MENU_MASTERS_BANKS = "masters.banks"
MENU_MASTERS_CUSTOMERS = "masters.customers"
MENU_MASTERS_SALESMEN = "masters.salesmen"
MENU_MASTERS_LAWYERS = "masters.lawyers"
MENU_MASTERS_CASE_TYPES = "masters.case_types"
MENU_MASTERS_DOCUMENT_LOCATIONS = "masters.document_locations"
MENU_ADMIN_USERS = "admin.users"
MENU_ADMIN_ROLES = "admin.roles"
MENU_ADMIN_EMAIL_LOG = "admin.email_log"
MENU_ADMIN_AUDIT_LOG = "admin.audit_log"
MENU_ADMIN_BACKUPS = "admin.backups"
MENU_ADMIN_SETTINGS = "admin.settings"
MENU_ADMIN_DIAGNOSTICS = "admin.diagnostics"
MENU_ADMIN_BULK_REASSIGN = "admin.bulk_reassign"
MENU_ADMIN_JOBS = "admin.jobs"

# Action IDs (case-level + cash-request-level)
ACTION_CASE_APPROVE_SALES_MGR = "case.approve.sales_mgr"
ACTION_CASE_APPROVE_DIV_MGR = "case.approve.div_mgr"
ACTION_CASE_APPROVE_AUDIT = "case.approve.audit"
ACTION_CASE_APPROVE_FM = "case.approve.fm"
ACTION_CASE_APPROVE_ED = "case.approve.ed"
ACTION_CASE_APPROVE_FINAL = "case.approve.final"
ACTION_CASE_LAWYER_APPROVE = "case.lawyer.approve"  # explicit lawyer sign-off after filing
ACTION_CASE_FILE = "case.file"
ACTION_CASE_CLOSE = "case.close"
ACTION_CASE_CREATE = "case.create"
ACTION_CASE_SIGNED_FORM_UPLOAD = "case.signed_form.upload"
ACTION_CASH_REQUEST = "cash.request"
ACTION_CASH_APPROVE = "cash.approve"
ACTION_CASH_PAY = "cash.pay"

_ALL_MASTERS = [
    MENU_MASTERS_DIVISIONS,
    MENU_MASTERS_BANKS,
    MENU_MASTERS_CUSTOMERS,
    MENU_MASTERS_SALESMEN,
    MENU_MASTERS_LAWYERS,
    MENU_MASTERS_CASE_TYPES,
    MENU_MASTERS_DOCUMENT_LOCATIONS,
]

_FULL_ADMIN_MENUS = [
    MENU_ADMIN_USERS,
    MENU_ADMIN_ROLES,
    MENU_ADMIN_EMAIL_LOG,
    MENU_ADMIN_AUDIT_LOG,
    MENU_ADMIN_BACKUPS,
    MENU_ADMIN_SETTINGS,
    MENU_ADMIN_DIAGNOSTICS,
    MENU_ADMIN_BULK_REASSIGN,
    MENU_ADMIN_JOBS,
]

SCOPE_ALL = "all"
SCOPE_OWN_DIVISIONS = "own_divisions"


# Role -> capability bundle
ROLE_CAPABILITIES: dict[str, dict] = {
    "Admin": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS, MENU_SCHEDULED_REPORTS,
            *_ALL_MASTERS,
            *_FULL_ADMIN_MENUS,
        ],
        "actions": [
            ACTION_CASE_CREATE,
            ACTION_CASE_APPROVE_SALES_MGR, ACTION_CASE_APPROVE_DIV_MGR,
            ACTION_CASE_APPROVE_AUDIT, ACTION_CASE_APPROVE_FM,
            ACTION_CASE_APPROVE_ED, ACTION_CASE_APPROVE_FINAL,
            ACTION_CASE_LAWYER_APPROVE, ACTION_CASE_FILE, ACTION_CASE_CLOSE,
            ACTION_CASE_SIGNED_FORM_UPLOAD,
            ACTION_CASH_REQUEST, ACTION_CASH_APPROVE, ACTION_CASH_PAY,
        ],
        "scope": SCOPE_ALL,
    },
    "Accountant": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS,
            MENU_MASTERS_CUSTOMERS, MENU_MASTERS_BANKS, MENU_MASTERS_SALESMEN,
            MENU_MASTERS_DOCUMENT_LOCATIONS,
        ],
        "actions": [
            ACTION_CASE_CREATE,
            ACTION_CASH_PAY,
        ],
        "scope": SCOPE_OWN_DIVISIONS,
    },
    "Sales Manager": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS,
        ],
        "actions": [
            ACTION_CASE_APPROVE_SALES_MGR,
        ],
        "scope": SCOPE_OWN_DIVISIONS,
    },
    "Division Manager": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS,
        ],
        "actions": [
            ACTION_CASE_APPROVE_DIV_MGR,
        ],
        "scope": SCOPE_OWN_DIVISIONS,
    },
    "Auditor": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS, MENU_SCHEDULED_REPORTS,
            MENU_ADMIN_AUDIT_LOG,
        ],
        "actions": [
            ACTION_CASE_APPROVE_AUDIT,
        ],
        "scope": SCOPE_ALL,
    },
    "Finance Manager": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS, MENU_SCHEDULED_REPORTS,
        ],
        "actions": [
            ACTION_CASE_APPROVE_FM,
            ACTION_CASE_SIGNED_FORM_UPLOAD,
            ACTION_CASH_APPROVE,
        ],
        "scope": SCOPE_OWN_DIVISIONS,
    },
    "Executive Director": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS, MENU_SCHEDULED_REPORTS,
        ],
        "actions": [
            ACTION_CASE_APPROVE_ED,
        ],
        "scope": SCOPE_OWN_DIVISIONS,
    },
    "Chairman / MD": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS, MENU_SCHEDULED_REPORTS,
        ],
        "actions": [
            ACTION_CASE_APPROVE_FINAL, ACTION_CASE_CLOSE,
        ],
        "scope": SCOPE_ALL,
    },
    "Lawyer": {
        "menus": [
            MENU_DASHBOARD, MENU_PROFILE,
            MENU_CASES, MENU_APPROVALS, MENU_HEARINGS, MENU_CASH_REQUESTS,
            MENU_REPORTS, MENU_SCHEDULED_REPORTS,
        ],
        "actions": [
            ACTION_CASE_LAWYER_APPROVE, ACTION_CASE_FILE,
            ACTION_CASE_SIGNED_FORM_UPLOAD,
            ACTION_CASH_REQUEST,
        ],
        "scope": SCOPE_ALL,
    },
}


def capabilities_for_role(role_name: str, is_super: bool) -> dict:
    """Return the ``{menus, actions, scope}`` bundle for a role.

    Super users always get the full Admin bundle. Unknown roles fall
    back to a minimal Dashboard + Profile bundle so a misconfigured
    role doesn't lock the user out of the app entirely.
    """
    if is_super:
        return dict(ROLE_CAPABILITIES["Admin"])
    if role_name in ROLE_CAPABILITIES:
        return dict(ROLE_CAPABILITIES[role_name])
    return {
        "menus": [MENU_DASHBOARD, MENU_PROFILE],
        "actions": [],
        "scope": SCOPE_OWN_DIVISIONS,
    }
