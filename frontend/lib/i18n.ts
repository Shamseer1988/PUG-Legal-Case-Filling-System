'use client';

import { useAuthStore } from './auth';

/** Lightweight i18n catalog.
 *
 *  Custom (not next-intl) so we can keep one file under source
 *  control and translate it offline with the legal team. Phase 43
 *  expanded the catalog from ~22 keys to the full set covering the
 *  sidebar, status/stage enums, page headings, table headers, form
 *  labels, filters, buttons, and common messages.
 *
 *  Conventions:
 *    - Keys are lowerCamelCase under namespaces (sidebar.*, cases.*).
 *    - English value mirrors what was hard-coded before, so screens
 *      that haven't been migrated still look the same in EN.
 *    - Arabic uses formal MSA suited to legal/government usage.
 *    - tStatus/tStage/tRole translate enum strings that arrive from
 *      the backend in English.
 */

export type Locale = 'en' | 'ar';

export const DEFAULT_LOCALE: Locale = 'en';
export const SUPPORTED_LOCALES: Locale[] = ['en', 'ar'];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  ar: 'العربية',
};

const EN: Record<string, string> = {
  // Sidebar group titles
  'sidebar.workspace': 'Workspace',
  'sidebar.transactions': 'Transactions',
  'sidebar.insights': 'Insights',
  'sidebar.masters': 'Masters',
  'sidebar.admin': 'Admin',

  // Sidebar items - workspace + transactions + insights
  'sidebar.dashboard': 'Dashboard',
  'sidebar.profile': 'My Profile',
  'sidebar.cases': 'Cases',
  'sidebar.approvals': 'Approvals Inbox',
  'sidebar.hearings': 'Hearings Calendar',
  'sidebar.cash_requests': 'Cash Requests',
  'sidebar.reports': 'Reports',
  'sidebar.scheduled_reports': 'Scheduled Reports',
  'sidebar.signout': 'Sign out',
  'sidebar.super': 'Super',
  'sidebar.collapse': 'Collapse sidebar',
  'sidebar.expand': 'Expand sidebar',

  // Sidebar - masters
  'sidebar.masters.divisions': 'Divisions',
  'sidebar.masters.banks': 'Banks',
  'sidebar.masters.customers': 'Customers',
  'sidebar.masters.salesmen': 'Salesmen',
  'sidebar.masters.lawyers': 'Lawyers',
  'sidebar.masters.case_types': 'Case Types',
  'sidebar.masters.document_locations': 'Document Locations',

  // Sidebar - admin
  'sidebar.admin.users': 'Users',
  'sidebar.admin.roles': 'Roles & Permissions',
  'sidebar.admin.email_log': 'Email Log',
  'sidebar.admin.audit_log': 'Audit Log',
  'sidebar.admin.backups': 'Backup & Restore',
  'sidebar.admin.settings': 'System Settings',
  'sidebar.admin.diagnostics': 'Health & Diagnostics',
  'sidebar.admin.jobs': 'Job Monitor',
  'sidebar.admin.bulk_reassign': 'Bulk Reassignment',

  // Common buttons
  'btn.save': 'Save',
  'btn.cancel': 'Cancel',
  'btn.delete': 'Delete',
  'btn.edit': 'Edit',
  'btn.new': 'New',
  'btn.search': 'Search',
  'btn.open': 'Open',
  'btn.print': 'Print',
  'btn.close': 'Close',
  'btn.add': 'Add',
  'btn.export': 'Export',
  'btn.download': 'Download',
  'btn.upload': 'Upload',
  'btn.submit': 'Submit',
  'btn.approve': 'Approve',
  'btn.reject': 'Reject',
  'btn.next': 'Next',
  'btn.previous': 'Previous',
  'btn.clear': 'Clear',
  'btn.apply': 'Apply',
  'btn.refresh': 'Refresh',
  'btn.confirm': 'Confirm',
  'btn.back': 'Back',
  'btn.view': 'View',
  'btn.run': 'Run',
  'btn.restore': 'Restore',
  'btn.test_connection': 'Test connection',

  // Common messages
  'common.loading': 'Loading...',
  'common.searching': 'Searching...',
  'common.no_results': 'No results.',
  'common.error': 'Error',
  'common.required': 'Required',
  'common.yes': 'Yes',
  'common.no': 'No',
  'common.all': 'All',
  'common.active': 'Active',
  'common.inactive': 'Inactive',
  'common.optional': '(optional)',
  'common.actions': 'Actions',
  'common.showing': 'Showing',
  'common.of': 'of',
  'common.results': 'results',
  'common.no_records': 'No records yet.',
  'common.confirm_delete': 'Delete this record?',
  'common.edit_record': 'Edit record',
  'common.new_record': 'New record',
  'common.all_companies': 'All Companies',
  'common.no_divisions': 'No divisions found.',

  // Status (case status enums, returned from backend as English strings)
  'status.Draft': 'Draft',
  'status.Submitted': 'Submitted',
  'status.In Review': 'In Review',
  'status.Clarification Requested': 'Clarification Requested',
  'status.Approved': 'Approved',
  'status.Filed': 'Filed',
  'status.Lawyer Approved': 'Lawyer Approved',
  'status.Rejected': 'Rejected',
  'status.Closed': 'Closed',

  // Stage (workflow stages, English from backend)
  'stage.Accountant': 'Accountant',
  'stage.Sales Manager': 'Sales Manager',
  'stage.Division Manager': 'Division Manager',
  'stage.Audit': 'Audit',
  'stage.Finance Manager': 'Finance Manager',
  'stage.Executive Director': 'Executive Director',
  'stage.Chairman / MD': 'Chairman / MD',
  'stage.Lawyer': 'Lawyer',
  'stage.Closed': 'Closed',

  // Roles (system roles, English from backend)
  'role.Accountant': 'Accountant',
  'role.Sales Manager': 'Sales Manager',
  'role.Division Manager': 'Division Manager',
  'role.Audit': 'Audit',
  'role.Finance Manager': 'Finance Manager',
  'role.Executive Director': 'Executive Director',
  'role.Chairman / MD': 'Chairman / MD',
  'role.Lawyer': 'Lawyer',
  'role.Admin': 'Admin',
  'role.Super': 'Super Admin',

  // Cases list page
  'cases.title': 'Cases',
  'cases.new': 'New Case',
  'cases.search_placeholder': 'Search case no / customer / notes',
  'cases.filters': 'Filters',
  'cases.filter.status': 'Status',
  'cases.filter.stage': 'Stage',
  'cases.filter.division': 'Division',
  'cases.filter.case_type': 'Case Type',
  'cases.filter.amount': 'Legal Amount',
  'cases.filter.created_between': 'Created Between',
  'cases.filter.min': 'Min',
  'cases.filter.max': 'Max',
  'cases.col.case_no': 'Case No',
  'cases.col.customer': 'Customer',
  'cases.col.division': 'Division',
  'cases.col.type': 'Type',
  'cases.col.legal_amount': 'Legal Amount',
  'cases.col.status': 'Status',
  'cases.col.stage': 'Stage',
  'cases.col.created': 'Created',
  'cases.type.criminal': 'Criminal',
  'cases.type.civil': 'Civil',
  'cases.empty.no_match': 'No cases match the active filters.',
  'cases.empty.no_cases': 'No cases yet.',

  // Case form labels (commonly used across new + edit)
  'caseform.customer': 'Customer',
  'caseform.division': 'Division',
  'caseform.customer_type': 'Customer Type',
  'caseform.division_manager': 'Division Manager',
  'caseform.salesman': 'Salesman',
  'caseform.police_case_no': 'Police Case No.',
  'caseform.court_case_no': 'Court Case No.',
  'caseform.case_date': 'Case Date',
  'caseform.case_type': 'Case Type',
  'caseform.legal_amount': 'Legal Filing Amount',
  'caseform.due_amount': 'Actual Due Amount',
  'caseform.bank': 'Bank',
  'caseform.bounced_amount': 'Bounced Amount',
  'caseform.cheque_no': 'Cheque No.',
  'caseform.cheque_date': 'Cheque Date',
  'caseform.notes': 'Notes',
  'caseform.partners': 'Partners',
  'caseform.signatories': 'Authorized Signatories',
  'caseform.attachments': 'Attachments',
  'caseform.is_criminal': 'Criminal',
  'caseform.is_civil': 'Civil',

  // Customers list
  'customers.title': 'Customers',
  'customers.new': 'New Customer',
  'customers.col.code': 'Code',
  'customers.col.name': 'Name',
  'customers.col.type': 'Type',
  'customers.col.phone': 'Phone',
  'customers.col.email': 'Email',
  'customers.col.address': 'Address',
  'customers.col.division': 'Division',
  'customers.col.salesman': 'Salesman',
  'customers.col.active': 'Active',
  'customers.col.partners': 'Partners',

  // Dashboard
  'dashboard.welcome': 'Welcome',
  'dashboard.live_overview': 'Live overview of legal cases scoped to your role.',
  'dashboard.kpi.total_cases': 'Total Cases',
  'dashboard.kpi.open': 'Open',
  'dashboard.kpi.approved_filed': 'Approved / Filed',
  'dashboard.kpi.legal_amount': 'Legal Amount',
  'dashboard.kpi.cash_paid': 'Cash Paid',
  'dashboard.kpi.my_inbox': 'My Inbox',
  'dashboard.kpi.overdue': 'overdue',
  'dashboard.panel.monthly_activity': 'Monthly Activity',
  'dashboard.panel.status_breakdown': 'Status Breakdown',
  'dashboard.panel.division_status': 'Division x Status',
  'dashboard.panel.upcoming_hearings': 'Upcoming Hearings (next 30 days)',
  'dashboard.panel.status_count': 'Status (count)',
  'dashboard.empty.no_cases': 'No cases yet',
  'dashboard.empty.no_hearings': 'No hearings scheduled',
  'dashboard.col.division': 'Division',
  'dashboard.col.total': 'Total',
  'dashboard.legend.created': 'Created',
  'dashboard.legend.approved': 'Approved',
  'dashboard.in_days': 'in {n}d',

  // Reports
  'reports.title': 'Reports',
  'reports.run': 'Run report',
  'reports.export_pdf': 'Export PDF',
  'reports.export_xlsx': 'Export Excel',
  'reports.export_csv': 'Export CSV',
  'reports.filter.from': 'From',
  'reports.filter.to': 'To',
  'reports.empty': 'No data for the selected period.',

  // Schedules
  'schedules.title': 'Scheduled Reports',
  'schedules.new': 'New schedule',
  'schedules.col.name': 'Name',
  'schedules.col.report': 'Report',
  'schedules.col.cron': 'Cron',
  'schedules.col.recipients': 'Recipients',
  'schedules.col.next_run': 'Next Run',
  'schedules.col.last_run': 'Last Run',
  'schedules.col.active': 'Active',

  // Masters - common
  'masters.divisions.title': 'Divisions',
  'masters.banks.title': 'Banks',
  'masters.customers.title': 'Customers',
  'masters.salesmen.title': 'Salesmen',
  'masters.lawyers.title': 'Lawyers',
  'masters.case_types.title': 'Case Types',
  'masters.document_locations.title': 'Document Locations',
  'masters.col.code': 'Code',
  'masters.col.name': 'Name',
  'masters.col.email': 'Email',
  'masters.col.phone': 'Phone',
  'masters.col.address': 'Address',
  'masters.col.description': 'Description',
  'masters.col.firm': 'Firm',
  'masters.col.bank_name': 'Bank Name',
  'masters.col.divisions': 'Divisions',
  'masters.col.division': 'Division',
  'masters.col.manager_email': 'Manager Email',
  'masters.col.accountant_email': 'Accountant Email',
  'masters.col.sales_manager_email': 'Sales Manager Email',
  'masters.col.storage': 'Storage',
  'masters.col.is_storage_help': 'Counts as storage (overdue report ignores docs parked here)',
  'masters.col.description_help': 'Description / where to find it',

  // Admin - common
  'admin.users.title': 'Users',
  'admin.roles.title': 'Roles & Permissions',
  'admin.email_log.title': 'Email Log',
  'admin.audit_log.title': 'Audit Log',
  'admin.backups.title': 'Backup & Restore',
  'admin.settings.title': 'System Settings',
  'admin.diagnostics.title': 'Health & Diagnostics',
  'admin.jobs.title': 'Job Monitor',
  'admin.bulk_reassign.title': 'Bulk Reassignment',
  'admin.audit.col.when': 'When',
  'admin.audit.col.action': 'Action',
  'admin.audit.col.entity': 'Entity',
  'admin.audit.col.actor': 'Actor',
  'admin.audit.col.summary': 'Summary',

  // Profile
  'profile.title': 'My Profile',
  'profile.language': 'Language',
  'profile.language.help':
    'Pick the language for the interface and the notification emails sent to you.',
  'profile.language.saved': 'Language preference saved.',
  'profile.full_name': 'Full Name',
  'profile.email': 'Email',
  'profile.role': 'Role',
  'profile.change_password': 'Change Password',
  'profile.current_password': 'Current Password',
  'profile.new_password': 'New Password',
  'profile.confirm_password': 'Confirm Password',
  'profile.two_factor': 'Two-Factor Authentication',
  'profile.signature': 'Signature',
  'profile.upload_signature': 'Upload Signature',
};

const AR: Record<string, string> = {
  // Sidebar group titles
  'sidebar.workspace': 'مساحة العمل',
  'sidebar.transactions': 'المعاملات',
  'sidebar.insights': 'التقارير والإحصاءات',
  'sidebar.masters': 'البيانات الرئيسية',
  'sidebar.admin': 'الإدارة',

  // Sidebar items
  'sidebar.dashboard': 'لوحة التحكم',
  'sidebar.profile': 'ملفي الشخصي',
  'sidebar.cases': 'القضايا',
  'sidebar.approvals': 'صندوق الموافقات',
  'sidebar.hearings': 'تقويم الجلسات',
  'sidebar.cash_requests': 'طلبات المصاريف',
  'sidebar.reports': 'التقارير',
  'sidebar.scheduled_reports': 'التقارير المجدولة',
  'sidebar.signout': 'تسجيل الخروج',
  'sidebar.super': 'مشرف عام',
  'sidebar.collapse': 'طي الشريط الجانبي',
  'sidebar.expand': 'توسيع الشريط الجانبي',

  // Masters submenu
  'sidebar.masters.divisions': 'الأقسام',
  'sidebar.masters.banks': 'البنوك',
  'sidebar.masters.customers': 'العملاء',
  'sidebar.masters.salesmen': 'مندوبو المبيعات',
  'sidebar.masters.lawyers': 'المحامون',
  'sidebar.masters.case_types': 'أنواع القضايا',
  'sidebar.masters.document_locations': 'مواقع المستندات',

  // Admin submenu
  'sidebar.admin.users': 'المستخدمون',
  'sidebar.admin.roles': 'الأدوار والصلاحيات',
  'sidebar.admin.email_log': 'سجل البريد الإلكتروني',
  'sidebar.admin.audit_log': 'سجل التدقيق',
  'sidebar.admin.backups': 'النسخ الاحتياطي والاستعادة',
  'sidebar.admin.settings': 'إعدادات النظام',
  'sidebar.admin.diagnostics': 'الصحة والتشخيص',
  'sidebar.admin.jobs': 'مراقبة المهام',
  'sidebar.admin.bulk_reassign': 'إعادة التعيين الجماعي',

  // Common buttons
  'btn.save': 'حفظ',
  'btn.cancel': 'إلغاء',
  'btn.delete': 'حذف',
  'btn.edit': 'تعديل',
  'btn.new': 'جديد',
  'btn.search': 'بحث',
  'btn.open': 'فتح',
  'btn.print': 'طباعة',
  'btn.close': 'إغلاق',
  'btn.add': 'إضافة',
  'btn.export': 'تصدير',
  'btn.download': 'تنزيل',
  'btn.upload': 'رفع',
  'btn.submit': 'إرسال',
  'btn.approve': 'موافقة',
  'btn.reject': 'رفض',
  'btn.next': 'التالي',
  'btn.previous': 'السابق',
  'btn.clear': 'مسح',
  'btn.apply': 'تطبيق',
  'btn.refresh': 'تحديث',
  'btn.confirm': 'تأكيد',
  'btn.back': 'رجوع',
  'btn.view': 'عرض',
  'btn.run': 'تشغيل',
  'btn.restore': 'استعادة',
  'btn.test_connection': 'اختبار الاتصال',

  // Common messages
  'common.loading': 'جارٍ التحميل...',
  'common.searching': 'جارٍ البحث...',
  'common.no_results': 'لا توجد نتائج.',
  'common.error': 'خطأ',
  'common.required': 'مطلوب',
  'common.yes': 'نعم',
  'common.no': 'لا',
  'common.all': 'الكل',
  'common.active': 'نشط',
  'common.inactive': 'غير نشط',
  'common.optional': '(اختياري)',
  'common.actions': 'إجراءات',
  'common.showing': 'عرض',
  'common.of': 'من',
  'common.results': 'النتائج',
  'common.no_records': 'لا توجد سجلات بعد.',
  'common.confirm_delete': 'حذف هذا السجل؟',
  'common.edit_record': 'تعديل السجل',
  'common.new_record': 'سجل جديد',
  'common.all_companies': 'جميع الشركات',
  'common.no_divisions': 'لا توجد أقسام.',

  // Status
  'status.Draft': 'مسودة',
  'status.Submitted': 'تم الإرسال',
  'status.In Review': 'قيد المراجعة',
  'status.Clarification Requested': 'مطلوب توضيح',
  'status.Approved': 'تمت الموافقة',
  'status.Filed': 'تم التقديم',
  'status.Lawyer Approved': 'موافقة المحامي',
  'status.Rejected': 'مرفوض',
  'status.Closed': 'مغلق',

  // Stage
  'stage.Accountant': 'المحاسب',
  'stage.Sales Manager': 'مدير المبيعات',
  'stage.Division Manager': 'مدير القسم',
  'stage.Audit': 'التدقيق',
  'stage.Finance Manager': 'المدير المالي',
  'stage.Executive Director': 'المدير التنفيذي',
  'stage.Chairman / MD': 'الرئيس / العضو المنتدب',
  'stage.Lawyer': 'المحامي',
  'stage.Closed': 'مغلق',

  // Roles
  'role.Accountant': 'محاسب',
  'role.Sales Manager': 'مدير مبيعات',
  'role.Division Manager': 'مدير قسم',
  'role.Audit': 'مدقق',
  'role.Finance Manager': 'مدير مالي',
  'role.Executive Director': 'مدير تنفيذي',
  'role.Chairman / MD': 'الرئيس / العضو المنتدب',
  'role.Lawyer': 'محامٍ',
  'role.Admin': 'مسؤول',
  'role.Super': 'مسؤول عام',

  // Cases list page
  'cases.title': 'القضايا',
  'cases.new': 'قضية جديدة',
  'cases.search_placeholder': 'البحث برقم القضية / العميل / الملاحظات',
  'cases.filters': 'عوامل التصفية',
  'cases.filter.status': 'الحالة',
  'cases.filter.stage': 'المرحلة',
  'cases.filter.division': 'القسم',
  'cases.filter.case_type': 'نوع القضية',
  'cases.filter.amount': 'مبلغ القضية',
  'cases.filter.created_between': 'تاريخ الإنشاء',
  'cases.filter.min': 'الأدنى',
  'cases.filter.max': 'الأعلى',
  'cases.col.case_no': 'رقم القضية',
  'cases.col.customer': 'العميل',
  'cases.col.division': 'القسم',
  'cases.col.type': 'النوع',
  'cases.col.legal_amount': 'مبلغ القضية',
  'cases.col.status': 'الحالة',
  'cases.col.stage': 'المرحلة',
  'cases.col.created': 'تاريخ الإنشاء',
  'cases.type.criminal': 'جزائية',
  'cases.type.civil': 'مدنية',
  'cases.empty.no_match': 'لا توجد قضايا مطابقة لعوامل التصفية المحددة.',
  'cases.empty.no_cases': 'لا توجد قضايا بعد.',

  // Case form labels
  'caseform.customer': 'العميل',
  'caseform.division': 'القسم',
  'caseform.customer_type': 'نوع العميل',
  'caseform.division_manager': 'مدير القسم',
  'caseform.salesman': 'مندوب المبيعات',
  'caseform.police_case_no': 'رقم قضية الشرطة',
  'caseform.court_case_no': 'رقم قضية المحكمة',
  'caseform.case_date': 'تاريخ القضية',
  'caseform.case_type': 'نوع القضية',
  'caseform.legal_amount': 'مبلغ التقديم القانوني',
  'caseform.due_amount': 'المبلغ المستحق الفعلي',
  'caseform.bank': 'البنك',
  'caseform.bounced_amount': 'مبلغ الشيك المرتجع',
  'caseform.cheque_no': 'رقم الشيك',
  'caseform.cheque_date': 'تاريخ الشيك',
  'caseform.notes': 'ملاحظات',
  'caseform.partners': 'الشركاء',
  'caseform.signatories': 'المفوضون بالتوقيع',
  'caseform.attachments': 'المرفقات',
  'caseform.is_criminal': 'جزائية',
  'caseform.is_civil': 'مدنية',

  // Customers list
  'customers.title': 'العملاء',
  'customers.new': 'عميل جديد',
  'customers.col.code': 'الرمز',
  'customers.col.name': 'الاسم',
  'customers.col.type': 'النوع',
  'customers.col.phone': 'الهاتف',
  'customers.col.email': 'البريد الإلكتروني',
  'customers.col.address': 'العنوان',
  'customers.col.division': 'القسم',
  'customers.col.salesman': 'مندوب المبيعات',
  'customers.col.active': 'نشط',
  'customers.col.partners': 'الشركاء',

  // Dashboard
  'dashboard.welcome': 'أهلاً بك',
  'dashboard.live_overview': 'نظرة عامة حية للقضايا القانونية ضمن نطاق دورك.',
  'dashboard.kpi.total_cases': 'إجمالي القضايا',
  'dashboard.kpi.open': 'مفتوحة',
  'dashboard.kpi.approved_filed': 'تمت الموافقة / تم التقديم',
  'dashboard.kpi.legal_amount': 'المبلغ القانوني',
  'dashboard.kpi.cash_paid': 'المبلغ المحصل',
  'dashboard.kpi.my_inbox': 'صندوق الوارد الخاص بي',
  'dashboard.kpi.overdue': 'متأخر',
  'dashboard.panel.monthly_activity': 'النشاط الشهري',
  'dashboard.panel.status_breakdown': 'توزيع الحالات',
  'dashboard.panel.division_status': 'القسم × الحالة',
  'dashboard.panel.upcoming_hearings': 'الجلسات القادمة (خلال 30 يوماً)',
  'dashboard.panel.status_count': 'الحالة (العدد)',
  'dashboard.empty.no_cases': 'لا توجد قضايا بعد',
  'dashboard.empty.no_hearings': 'لا توجد جلسات مجدولة',
  'dashboard.col.division': 'القسم',
  'dashboard.col.total': 'الإجمالي',
  'dashboard.legend.created': 'تم الإنشاء',
  'dashboard.legend.approved': 'تمت الموافقة',
  'dashboard.in_days': 'خلال {n} يوم',

  // Reports
  'reports.title': 'التقارير',
  'reports.run': 'تشغيل التقرير',
  'reports.export_pdf': 'تصدير PDF',
  'reports.export_xlsx': 'تصدير Excel',
  'reports.export_csv': 'تصدير CSV',
  'reports.filter.from': 'من',
  'reports.filter.to': 'إلى',
  'reports.empty': 'لا توجد بيانات للفترة المحددة.',

  // Schedules
  'schedules.title': 'التقارير المجدولة',
  'schedules.new': 'جدولة جديدة',
  'schedules.col.name': 'الاسم',
  'schedules.col.report': 'التقرير',
  'schedules.col.cron': 'الجدولة',
  'schedules.col.recipients': 'المستلمون',
  'schedules.col.next_run': 'التشغيل القادم',
  'schedules.col.last_run': 'آخر تشغيل',
  'schedules.col.active': 'نشط',

  // Masters page titles
  'masters.divisions.title': 'الأقسام',
  'masters.banks.title': 'البنوك',
  'masters.customers.title': 'العملاء',
  'masters.salesmen.title': 'مندوبو المبيعات',
  'masters.lawyers.title': 'المحامون',
  'masters.case_types.title': 'أنواع القضايا',
  'masters.document_locations.title': 'مواقع المستندات',
  'masters.col.code': 'الرمز',
  'masters.col.name': 'الاسم',
  'masters.col.email': 'البريد الإلكتروني',
  'masters.col.phone': 'الهاتف',
  'masters.col.address': 'العنوان',
  'masters.col.description': 'الوصف',
  'masters.col.firm': 'المكتب',
  'masters.col.bank_name': 'اسم البنك',
  'masters.col.divisions': 'الأقسام',
  'masters.col.division': 'القسم',
  'masters.col.manager_email': 'البريد الإلكتروني للمدير',
  'masters.col.accountant_email': 'البريد الإلكتروني للمحاسب',
  'masters.col.sales_manager_email': 'البريد الإلكتروني لمدير المبيعات',
  'masters.col.storage': 'مخزن',
  'masters.col.is_storage_help': 'يُعتبر مخزناً (تقرير المتأخرات يتجاهل المستندات الموضوعة هنا)',
  'masters.col.description_help': 'الوصف / أين تجدها',

  // Admin page titles + audit columns
  'admin.users.title': 'المستخدمون',
  'admin.roles.title': 'الأدوار والصلاحيات',
  'admin.email_log.title': 'سجل البريد الإلكتروني',
  'admin.audit_log.title': 'سجل التدقيق',
  'admin.backups.title': 'النسخ الاحتياطي والاستعادة',
  'admin.settings.title': 'إعدادات النظام',
  'admin.diagnostics.title': 'الصحة والتشخيص',
  'admin.jobs.title': 'مراقبة المهام',
  'admin.bulk_reassign.title': 'إعادة التعيين الجماعي',
  'admin.audit.col.when': 'الوقت',
  'admin.audit.col.action': 'الإجراء',
  'admin.audit.col.entity': 'الكيان',
  'admin.audit.col.actor': 'المنفذ',
  'admin.audit.col.summary': 'الملخص',

  // Profile
  'profile.title': 'ملفي الشخصي',
  'profile.language': 'اللغة',
  'profile.language.help':
    'اختر لغة الواجهة ولغة رسائل الإشعارات التي تصلك بالبريد الإلكتروني.',
  'profile.language.saved': 'تم حفظ تفضيل اللغة.',
  'profile.full_name': 'الاسم الكامل',
  'profile.email': 'البريد الإلكتروني',
  'profile.role': 'الدور',
  'profile.change_password': 'تغيير كلمة المرور',
  'profile.current_password': 'كلمة المرور الحالية',
  'profile.new_password': 'كلمة المرور الجديدة',
  'profile.confirm_password': 'تأكيد كلمة المرور',
  'profile.two_factor': 'المصادقة الثنائية',
  'profile.signature': 'التوقيع',
  'profile.upload_signature': 'رفع التوقيع',
};

const MESSAGES: Record<Locale, Record<string, string>> = { en: EN, ar: AR };

export function useLocale(): Locale {
  const me = useAuthStore((s) => s.me);
  const raw = (me?.locale ?? DEFAULT_LOCALE) as Locale;
  return SUPPORTED_LOCALES.includes(raw) ? raw : DEFAULT_LOCALE;
}

export function isRtl(locale: Locale): boolean {
  return locale === 'ar';
}

/** Look up a translation. Falls back to English, then to the key
 *  itself so missing strings are visible and fixable. */
export function tFor(locale: Locale, key: string): string {
  return MESSAGES[locale]?.[key] ?? MESSAGES.en[key] ?? key;
}

/** Translate-in-the-component hook. */
export function useT(): (key: string) => string {
  const locale = useLocale();
  return (key: string) => tFor(locale, key);
}

/** Map a backend status enum string (English) to a localized
 *  display label. Unknown values pass through unchanged. */
export function tStatus(locale: Locale, status: string | null | undefined): string {
  if (!status) return '';
  return MESSAGES[locale]?.[`status.${status}`] ?? status;
}

/** Map a backend workflow stage to a localized display label. */
export function tStage(locale: Locale, stage: string | null | undefined): string {
  if (!stage) return '';
  return MESSAGES[locale]?.[`stage.${stage}`] ?? stage;
}

/** Map a role string (English) to a localized display label. */
export function tRole(locale: Locale, role: string | null | undefined): string {
  if (!role) return '';
  return MESSAGES[locale]?.[`role.${role}`] ?? role;
}
