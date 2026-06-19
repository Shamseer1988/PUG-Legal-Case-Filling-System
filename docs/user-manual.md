# User Manual

A concise guide for everyday users of the PUG Legal Case Control
System. Open this from the **Help** menu inside the app (or share it
with new hires).

## 1. Roles at a glance

| Role | Can | Cannot |
|---|---|---|
| Accountant | Create cases, attach docs, submit, respond to clarifications | Approve, file in court |
| Sales Manager | Approve at the Sales Manager stage | Edit case content |
| Division Manager | Approve at the Division Manager stage | Edit case content |
| Auditor | Approve at the Audit stage | Edit case content |
| Finance Manager | Approve at FM, approve cash requests | File in court |
| Executive Director | Approve at the ED stage | - |
| Chairman / MD | Final approval | - |
| Lawyer | Court filing, hearings, cash requests | Approval workflow |
| Admin | Everything (system-wide) | - |

## 2. Sign in

1. Open the app URL (your administrator will send it to you).
2. Enter email + password.
3. If you have 2FA, enter the 6-digit code from your authenticator app.

> Your administrator can reset your password from **Admin -> Users**.

## 3. Filing a new case (Accountant)

1. Sidebar -> **Transactions -> Cases -> New Case**.
2. Tick **Criminal**, **Civil** or **Both**.
3. Choose the customer, division, salesman and bank from the dropdowns
   (they come from the Masters menu - ask Admin to add a missing entry).
4. Fill in the amounts and deposit date.
5. **Add Cheque** (the **+** button) for each cheque - number, bank,
   amount, date, type, bounce reason.
6. Pick signatories: Sales Manager, Division Manager, FM, ED, Chairman,
   Lawyer.
7. **Save Draft** as you go. **Save & Submit** when complete - the case
   becomes immutable and moves to the Sales Manager's inbox.
8. Use **Attach Files** to add supporting documents (bank statements,
   contracts, govt letters).
9. **Print** for the physical signing copy.

## 4. Approval workflow

Cases progress in a fixed chain:

```
Accountant
   |
   v
Sales Manager  ->  Division Manager  ->  Audit  ->  FM
   ->  ED  ->  Chairman / MD  ->  Lawyer
```

At every stage the assigned signatory has three options:

- **Approve** -> the case advances to the next stage.
- **Request Clarification** -> the case returns to the accountant with a
  question. Once they **Resubmit**, the case comes back to you.
- **Reject** (reason required) -> the case is terminated.

Find your work in **Transactions -> Approvals Inbox**. SLA-breached
cases show a red **Overdue** badge.

## 5. Court filing and hearings (Lawyer)

Once Chairman / MD has approved, the case status flips to **Approved**
and three panels appear on the case page:

- **Court Filing** -> record Police Case No., Court Case No., filed
  date and notes. Saving this flips the case to **Filed**.
- **Hearings** -> add hearings (date, location, type, outcome) and the
  next-hearing date. They show up on **Hearings Calendar** and in the
  Hearing Schedule report.
- **Cash Requests & Expenses** -> request cash for filing fees, process
  servers, etc. FM approves, the Accountant pays with a receipt.

## 6. Reports

**Insights -> Reports** lists every report. Pick filters, click **Run**
to preview, then **Excel** or **PDF** to download. Use **Print** for an
A4-tuned printable version.

For recurring exports, go to **Insights -> Scheduled Reports -> New
Schedule**. Pick the report, a cron expression, recipients, formats
(PDF / Excel) and notes. Save and the system will email a branded
summary on the cadence you chose.

## 7. Notifications

The bell icon (top-right) shows in-app alerts. Click the dot to mark
all as read. Email notifications are sent in parallel - your
administrator manages the SMTP configuration.

## 8. Profile & 2FA

**Profile** (from the sidebar) shows your identity and lets you turn on
**Two-Factor Authentication**:

1. Click **Set up 2FA**.
2. Scan the QR code with Google Authenticator, 1Password, Authy, etc.
3. Enter the 6-digit code your app shows and click **Activate**.

From the next sign-in onwards, you'll be asked for the code.

## 9. Help

If something doesn't look right:

1. Take a screenshot.
2. Note the time and the URL.
3. Send both to your administrator. They have access to the audit log
   and email log to investigate.

For administrators, see `docs/runbooks/on-call.md`.
