"""Permission string constants and role presets used by the seed."""

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
CASES_FILE = "cases:file"
HEARINGS_WRITE = "hearings:write"
EXPENSES_REQUEST = "expenses:request"
EXPENSES_APPROVE = "expenses:approve"
EXPENSES_PAY = "expenses:pay"

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
    ],
    "Sales Manager": [
        CASES_READ,
        CASES_APPROVE_SALES_MGR,
        MASTERS_READ,
    ],
    "Division Manager": [
        CASES_READ,
        CASES_APPROVE_DIV_MGR,
        MASTERS_READ,
    ],
    "Auditor": [
        CASES_READ,
        CASES_APPROVE_AUDIT,
        ADMIN_AUDIT_LOG,
        MASTERS_READ,
    ],
    "Finance Manager": [
        CASES_READ,
        CASES_APPROVE_FM,
        EXPENSES_APPROVE,
        MASTERS_READ,
    ],
    "Executive Director": [
        CASES_READ,
        CASES_APPROVE_ED,
        MASTERS_READ,
    ],
    "Chairman / MD": [
        CASES_READ,
        CASES_APPROVE_FINAL,
        MASTERS_READ,
    ],
    "Lawyer": [
        CASES_READ,
        CASES_FILE,
        HEARINGS_WRITE,
        EXPENSES_REQUEST,
        MASTERS_READ,
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
