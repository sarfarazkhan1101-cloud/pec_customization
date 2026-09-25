### PEW Customizations

Tender pipeline on the standard Opportunity, Project handoff and PEC project-execution customizations for PEW Engineering on ERPNext v16.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app pew_customizations
```

### Tender pipeline (Opportunity)

Everything below ships as fixtures and code and arrives with `bench migrate`, except the site-specific
setup at the end.

- **Stages**: 7 Sales Stages (Cold → Closure (Won)) ordered by `Sales Stage.pew_stage_order`;
  `Opportunity.pew_stage_index` fetches it and drives every section's `depends_on`.
- **Gates**: `pew_customizations/crm/config.py` (`EXIT_GATES`, `ENTRY_GATES`) is the single list of
  checklist items. The server enforces it on every forward move, including Kanban drags and API writes.
- **Lost**: standard Declare Lost dialog (button added); the deal keeps its stage, gets a red "Lost" tag
  and becomes read-only except for Sales Managers.
- **Won**: moving to Closure (Won) (Sales Manager only) sets status Converted and creates one Project in
  the "Pending" workflow state with the Technical documents only.
- **Execution Team**: the Project's standard Users table. After approval, each member gets a User
  Permission on the Project.
- **Kanban**: "Tender Pipeline" board on `sales_stage`, maintained by `after_migrate`.

Changing fields or settings on a development site:

```bash
bench --site <site> execute pew_customizations.crm.setup.apply_customizations
bench --site <site> export-fixtures --app pew_customizations
bench --site <site> run-tests --module pew_customizations.tests.test_opportunity_pipeline
```

#### Site-specific setup (not fixtures)

1. **Email Account** (Google Workspace shared mailbox, e.g. `tenders@<domain>`):
   - Service "GMail"; Authentication "OAuth" with a Connected App (Google Cloud OAuth client, scope
     `https://mail.google.com/`, redirect URI
     `https://<site>/api/method/frappe.integrations.doctype.connected_app.connected_app.callback`).
     Fallback: 2-Step Verification + App Password.
   - Incoming: IMAP, folder `INBOX` with **Append To left empty** (otherwise every unmatched email
     creates an Opportunity), sync "UNSEEN", Create Contact on, **Enable Automatic Linking** on.
   - Outgoing: default outgoing, always use the account's address as sender, "Append Emails to Sent
     Folder" off (Gmail already keeps sent mail).
   - Replies to emails sent from the Opportunity thread automatically; subjects carrying
     `(#CRM-OPP-…)` are linked by `crm/communication.py`; people emailing from Gmail directly BCC the
     `tenders+opportunity=<name>@<domain>` address shown in the form sidebar. Anything else is linked
     with **Actions → Link Emails** on the Opportunity.
2. **Assignment Rule** "Estimation Team" on Opportunity: assign condition
   `sales_stage == "Inquiry / Tender"`, rule Round Robin, users = the estimation team. Leaving
   Inquiry / Tender requires the deal to have been assigned.
3. **Users**: Execution Team members need a role that can read Project (e.g. Projects User); managers
   who must see every Project keep Projects Manager (never restricted).

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/pew_customizations
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
