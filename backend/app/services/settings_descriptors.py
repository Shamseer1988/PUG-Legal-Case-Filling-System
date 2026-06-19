"""Static descriptor of every settings group + field.

The frontend reads this and renders a tabbed form. The backend uses it
to validate keys, default values and the ``sensitive`` flag.

Fields:
    key       - unique full key e.g. "smtp.host"
    label
    type      - text | textarea | password | email | number | checkbox |
                color | select | url
    default
    options   - for select fields
    env       - name of the env-var that supplies the runtime fallback
    sensitive - encrypted at rest if True
    placeholder, help - UI hints
"""

from __future__ import annotations

from typing import Any


GROUPS: list[dict[str, Any]] = [
    {
        "key": "company",
        "name": "Company & Branding",
        "description": "Branded headers, colours and email signature.",
        "icon": "Building2",
        "fields": [
            {"key": "company.name", "label": "Company Name", "type": "text",
             "default": "Paris United Group Holding", "env": "BRAND_COMPANY_NAME"},
            {"key": "company.address", "label": "Address", "type": "textarea"},
            {"key": "company.trn", "label": "Tax Registration No.", "type": "text"},
            {"key": "company.logo_url", "label": "Logo URL", "type": "url"},
            {"key": "company.app_url", "label": "App Base URL", "type": "url",
             "env": "BRAND_APP_URL", "default": "http://127.0.0.1:3000"},
            {"key": "company.theme_primary", "label": "Primary Color (gold)",
             "type": "color", "default": "#c9a14a"},
            {"key": "company.theme_secondary", "label": "Secondary Color (navy)",
             "type": "color", "default": "#1a234a"},
            {"key": "company.email_signature", "label": "Email Signature",
             "type": "textarea"},
        ],
    },
    {
        "key": "smtp",
        "name": "Email (SMTP)",
        "description": "Outbound email server. Use the Test Send button to verify.",
        "icon": "Mail",
        "actions": ["test_send"],
        "fields": [
            {"key": "smtp.host", "label": "Host", "type": "text", "env": "SMTP_HOST"},
            {"key": "smtp.port", "label": "Port", "type": "number",
             "default": 587, "env": "SMTP_PORT"},
            {"key": "smtp.use_tls", "label": "Use TLS", "type": "checkbox",
             "default": True, "env": "SMTP_USE_TLS"},
            {"key": "smtp.username", "label": "Username", "type": "text",
             "env": "SMTP_USERNAME"},
            {"key": "smtp.password", "label": "Password", "type": "password",
             "sensitive": True, "env": "SMTP_PASSWORD"},
            {"key": "smtp.from_email", "label": "From Email", "type": "email",
             "default": "no-reply@pug.local", "env": "SMTP_FROM_EMAIL"},
            {"key": "smtp.from_name", "label": "From Name", "type": "text",
             "default": "PUG Legal Case Control System", "env": "SMTP_FROM_NAME"},
        ],
    },
    {
        "key": "ai",
        "name": "AI Configuration",
        "description": "Optional AI assistance (case summary, OCR, status hints).",
        "icon": "Sparkles",
        "fields": [
            {"key": "ai.provider", "label": "Provider", "type": "select",
             "options": ["", "Anthropic Claude", "OpenAI"], "default": ""},
            {"key": "ai.model", "label": "Model ID", "type": "text",
             "placeholder": "claude-opus-4-7"},
            {"key": "ai.api_key", "label": "API Key", "type": "password",
             "sensitive": True},
            {"key": "ai.use_cases", "label": "Enabled Use-Cases", "type": "text",
             "placeholder": "case_summary, ocr, status_hint",
             "help": "Comma-separated, forward-looking."},
            {"key": "ai.daily_token_cap", "label": "Daily Token Cap",
             "type": "number", "default": 200000},
        ],
    },
    {
        "key": "numbering",
        "name": "Numbering & Sequences",
        "description": "Code formats for cases, divisions, etc.",
        "icon": "Tag",
        "fields": [
            {"key": "numbering.case_prefix", "label": "Case No. Prefix",
             "type": "text", "default": "PUG-LEGAL"},
            {"key": "numbering.case_padding", "label": "Sequence Padding",
             "type": "number", "default": 4},
            {"key": "numbering.case_reset_yearly", "label": "Reset Sequence Yearly",
             "type": "checkbox", "default": True},
            {"key": "numbering.division_code_prefix", "label": "Division Code Prefix",
             "type": "text"},
        ],
    },
    {
        "key": "workflow",
        "name": "Workflow Rules",
        "description": "Per-stage SLA overrides (hours).",
        "icon": "Briefcase",
        "fields": [
            {"key": "workflow.sla.sales_mgr", "label": "Sales Manager SLA (h)",
             "type": "number", "default": 24},
            {"key": "workflow.sla.div_mgr", "label": "Division Manager SLA (h)",
             "type": "number", "default": 24},
            {"key": "workflow.sla.audit", "label": "Audit SLA (h)",
             "type": "number", "default": 48},
            {"key": "workflow.sla.fm", "label": "Finance Manager SLA (h)",
             "type": "number", "default": 24},
            {"key": "workflow.sla.ed", "label": "ED SLA (h)",
             "type": "number", "default": 48},
            {"key": "workflow.sla.chairman", "label": "Chairman/MD SLA (h)",
             "type": "number", "default": 72},
            {"key": "workflow.auto_escalate", "label": "Auto-escalate on SLA breach",
             "type": "checkbox", "default": False},
        ],
    },
    {
        "key": "security",
        "name": "Security",
        "description": "Authentication and session policy.",
        "icon": "Lock",
        "fields": [
            {"key": "security.password_min_length", "label": "Password Min Length",
             "type": "number", "default": 8},
            {"key": "security.password_expiry_days",
             "label": "Password Expiry (days, 0 = never)",
             "type": "number", "default": 0},
            {"key": "security.require_2fa_roles",
             "label": "Roles requiring 2FA (comma-separated)",
             "type": "text",
             "placeholder": "Admin, Chairman / MD"},
            {"key": "security.session_timeout_minutes",
             "label": "Session Timeout (min)",
             "type": "number", "default": 60},
            {"key": "security.ip_allowlist",
             "label": "IP Allow-list (comma-separated)",
             "type": "text"},
        ],
    },
    {
        "key": "backup",
        "name": "Backup Policy",
        "description": "Scheduled backups + retention (Phase 9 engine).",
        "icon": "HardDrive",
        "fields": [
            {"key": "backup.schedule_cron",
             "label": "Backup Cron (UTC)", "type": "text",
             "default": "0 2 * * *",
             "help": "Standard 5-field cron; daily 02:00 UTC by default."},
            {"key": "backup.retention_daily",
             "label": "Daily backups to keep",
             "type": "number", "default": 7},
            {"key": "backup.retention_weekly",
             "label": "Weekly backups to keep",
             "type": "number", "default": 4},
            {"key": "backup.retention_monthly",
             "label": "Monthly backups to keep",
             "type": "number", "default": 12},
            {"key": "backup.offsite_s3_url",
             "label": "Offsite S3 URL",
             "type": "text",
             "placeholder": "s3://bucket/path"},
            {"key": "backup.offsite_s3_access_key",
             "label": "Offsite S3 Access Key",
             "type": "password", "sensitive": True},
            {"key": "backup.offsite_s3_secret_key",
             "label": "Offsite S3 Secret Key",
             "type": "password", "sensitive": True},
        ],
    },
    {
        "key": "notifications",
        "name": "Notifications",
        "description": "Channels and digest cadence for system events.",
        "icon": "Bell",
        "fields": [
            {"key": "notifications.email_enabled", "label": "Email Notifications",
             "type": "checkbox", "default": True},
            {"key": "notifications.inapp_enabled", "label": "In-App Bell",
             "type": "checkbox", "default": True},
            {"key": "notifications.digest_cadence",
             "label": "Digest Cadence", "type": "select",
             "options": ["realtime", "hourly", "daily"], "default": "realtime"},
            {"key": "notifications.quiet_hours_start",
             "label": "Quiet Hours Start (UTC, 0-23)",
             "type": "number", "default": 0},
            {"key": "notifications.quiet_hours_end",
             "label": "Quiet Hours End (UTC, 0-23)",
             "type": "number", "default": 0},
        ],
    },
    {
        "key": "appearance",
        "name": "Appearance",
        "description": "Defaults that apply to new sessions.",
        "icon": "Palette",
        "fields": [
            {"key": "appearance.default_theme", "label": "Default Theme",
             "type": "select", "options": ["system", "light", "dark"],
             "default": "system"},
            {"key": "appearance.date_format", "label": "Date Format",
             "type": "select",
             "options": ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"],
             "default": "YYYY-MM-DD"},
            {"key": "appearance.number_format", "label": "Number Format",
             "type": "select", "options": ["1,234.56", "1.234,56", "1 234,56"],
             "default": "1,234.56"},
            {"key": "appearance.language", "label": "Default Language",
             "type": "select", "options": ["en", "ar"], "default": "en"},
        ],
    },
    {
        "key": "integrations",
        "name": "Integrations",
        "description": "External services (S3, SMS, webhooks).",
        "icon": "Plug",
        "fields": [
            {"key": "integrations.s3_endpoint", "label": "S3 Endpoint",
             "type": "url",
             "placeholder": "https://s3.amazonaws.com"},
            {"key": "integrations.s3_bucket", "label": "S3 Bucket",
             "type": "text"},
            {"key": "integrations.s3_access_key", "label": "S3 Access Key",
             "type": "password", "sensitive": True},
            {"key": "integrations.s3_secret_key", "label": "S3 Secret Key",
             "type": "password", "sensitive": True},
            {"key": "integrations.sms_provider", "label": "SMS Provider",
             "type": "select", "options": ["", "Twilio", "AWS SNS"], "default": ""},
            {"key": "integrations.sms_api_key", "label": "SMS API Key",
             "type": "password", "sensitive": True},
            {"key": "integrations.webhook_url", "label": "Webhook URL",
             "type": "url"},
        ],
    },
    {
        "key": "data",
        "name": "Data Management",
        "description": "Retention and purge policies.",
        "icon": "Database",
        "fields": [
            {"key": "data.recycle_bin_days", "label": "Recycle Bin Retention (days)",
             "type": "number", "default": 30},
            {"key": "data.log_purge_days",
             "label": "Email/Notification Log Retention (days)",
             "type": "number", "default": 180},
            {"key": "data.bulk_import_path",
             "label": "Default Bulk Import Path", "type": "text"},
        ],
    },
    {
        "key": "maintenance",
        "name": "Maintenance",
        "description": "Read-only banner + cache controls.",
        "icon": "Wrench",
        "actions": ["flush_cache"],
        "fields": [
            {"key": "maintenance.mode", "label": "Maintenance Mode",
             "type": "checkbox", "default": False},
            {"key": "maintenance.banner",
             "label": "Banner Message", "type": "textarea",
             "placeholder": "Read-only system maintenance from 22:00 to 23:00 UTC"},
            {"key": "maintenance.contact_email", "label": "Support Contact Email",
             "type": "email"},
        ],
    },
]


# Lookup by full key
def field_for(key: str) -> dict | None:
    for g in GROUPS:
        for f in g["fields"]:
            if f["key"] == key:
                return f
    return None


def group_for(group_key: str) -> dict | None:
    for g in GROUPS:
        if g["key"] == group_key:
            return g
    return None
