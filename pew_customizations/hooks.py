app_name = "pew_customizations"
app_title = "PEW Customizations"
app_publisher = "PEW Engineering & Consultancy Pvt Ltd"
app_description = "Tender pipeline on Opportunity, Project handoff and PEC project-execution customizations for PEW Engineering on ERPNext v16"
app_email = "admin@example.com"
app_license = "mit"

# Fixtures
# --------
# Scoped precisely to records this app owns: Custom Fields and Property Setters by record name
# (File also carries the Drive app's custom fields, Opportunity may carry other apps').

# Names starting with "_" are not registered as hooks (hooks are cached by pickling them).
from pew_customizations.crm import config as _crm  # noqa: E402
from pew_customizations.crm.customizations import get_custom_field_names as _crm_fields  # noqa: E402
from pew_customizations.crm.customizations import get_property_setter_names as _crm_ps  # noqa: E402
from pew_customizations.setup.install import (  # noqa: E402
	LIFECYCLE_TASKS,
	MARKET_SEGMENTS,
	NOTIFICATION_REVISION_APPROVED,
	NOTIFICATION_REVISION_REJECTED,
	NOTIFICATION_REVISION_SUBMITTED,
	NOTIFICATION_TASK_OVERDUE,
	PEC_REVISION_WORKFLOW_NAME,
	PEC_ROLES,
	PROJECT_TEMPLATE_NAME,
	SCOPE_TEMPLATE_NAMES,
	SCOPE_TEMPLATE_TASKS,
	WORKFLOW_NAME,
	get_custom_field_names as _pec_fields,
)

# Files are numbered in the order listed below and import in that order: Custom Fields before the
# records that use them (Sales Stage.pew_stage_order), Task before Project Template.
fixture_auto_order = True

_ALL_TEMPLATE_TASK_SUBJECTS = [t[0] for t in LIFECYCLE_TASKS] + [t[0] for t in SCOPE_TEMPLATE_TASKS]
_ALL_PROJECT_TEMPLATE_NAMES = [PROJECT_TEMPLATE_NAME, *SCOPE_TEMPLATE_NAMES.values()]
_ALL_NOTIFICATION_NAMES = [
	*_crm.NOTIFICATIONS,
	NOTIFICATION_REVISION_SUBMITTED,
	NOTIFICATION_REVISION_REJECTED,
	NOTIFICATION_REVISION_APPROVED,
	NOTIFICATION_TASK_OVERDUE,
]

fixtures = [
	{"dt": "Custom Field", "filters": [["name", "in", _pec_fields() + _crm_fields()]]},
	{
		"dt": "Property Setter",
		"filters": [["name", "in", ["Project-naming_series-options", *_crm_ps()]]],
	},
	{"dt": "Role", "filters": [["name", "in", PEC_ROLES]]},
	{"dt": "Sales Stage", "filters": [["name", "in", _crm.PIPELINE_STAGES]]},
	{"dt": "Market Segment", "filters": [["name", "in", MARKET_SEGMENTS]]},
	{"dt": "Notification", "filters": [["name", "in", _ALL_NOTIFICATION_NAMES]]},
	{"dt": "Workflow", "filters": [["name", "in", [WORKFLOW_NAME, PEC_REVISION_WORKFLOW_NAME]]]},
	{"dt": "Opportunity Lost Reason", "filters": [["name", "in", _crm.LOST_REASONS]]},
	{
		"dt": "Task",
		"filters": [["is_template", "=", 1], ["subject", "in", _ALL_TEMPLATE_TASK_SUBJECTS]],
	},
	{"dt": "Project Template", "filters": [["name", "in", _ALL_PROJECT_TEMPLATE_NAMES]]},
	{"dt": "UTM Source", "filters": [["name", "in", _crm.LEAD_SOURCES]]},
	# Opportunity's permissions incl. level 1 (Work Order / Client PO) for Sales Manager
	{"dt": "Custom DocPerm", "filters": [["parent", "=", "Opportunity"]]},
]

# Document Events
# ---------------
doc_events = {
	"PEC Revision": {
		"on_update": "pew_customizations.pec_revision_utils.sync_dci_rollup",
		"on_submit": "pew_customizations.pec_revision_utils.sync_dci_rollup",
		"on_cancel": "pew_customizations.pec_revision_utils.sync_dci_rollup",
	},
	"Task": {
		"on_update": "pew_customizations.utils.sync_scope_from_tasks",
		"on_trash": "pew_customizations.utils.sync_scope_from_tasks",
	},
	"Scope": {
		"on_update": "pew_customizations.utils.sync_project_from_scopes",
		"on_trash": "pew_customizations.utils.sync_project_from_scopes",
	},
	"Opportunity": {
		"onload": "pew_customizations.crm.opportunity.onload",
		"validate": "pew_customizations.crm.opportunity.validate",
		"on_update": "pew_customizations.crm.opportunity.on_update",
		"on_trash": "pew_customizations.crm.opportunity.on_trash",
	},
	"Customer": {
		"onload": "pew_customizations.crm.customer.onload",
		"after_insert": "pew_customizations.crm.customer.repoint_source_opportunity",
	},
	"Communication": {
		"before_insert": "pew_customizations.crm.communication.link_by_subject_tag",
	},
	"Project": {
		"on_update": "pew_customizations.projects.project_team.sync_team_access",
		"on_trash": "pew_customizations.projects.project_team.revoke_all",
	},
}

# Work Order / Client PO files are readable by Sales Managers only
has_permission = {
	"File": "pew_customizations.crm.file.has_permission",
}

after_migrate = ["pew_customizations.crm.setup.after_migrate"]

# Dashboard Connections
# ----------------------
override_doctype_dashboards = {
	"Project": "pew_customizations.dashboard.get_project_dashboard_data",
	"Task": "pew_customizations.dashboard.get_task_dashboard_data",
	"Opportunity": "pew_customizations.dashboard.get_opportunity_dashboard_data",
}

# Doctype JS
# ----------
doctype_js = {
	"Scope": "public/js/scope.js",
	"DCI": "public/js/dci.js",
	"PEC Revision": "public/js/pec_revision.js",
	"Opportunity": "public/js/opportunity.js",
	"Customer": "public/js/customer.js",
}

doctype_list_js = {
	"Scope": "public/js/scope_list.js",
}

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pew_customizations",
# 		"logo": "/assets/pew_customizations/logo.png",
# 		"title": "PEW Customizations",
# 		"route": "/pew_customizations",
# 		"has_permission": "pew_customizations.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/pew_customizations/css/pew_customizations.css"
# app_include_js = "/assets/pew_customizations/js/pew_customizations.js"

# include js, css files in header of web template
# web_include_css = "/assets/pew_customizations/css/pew_customizations.css"
# web_include_js = "/assets/pew_customizations/js/pew_customizations.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pew_customizations/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pew_customizations/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "pew_customizations.utils.jinja_methods",
# 	"filters": "pew_customizations.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "pew_customizations.install.before_install"
# after_install = "pew_customizations.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "pew_customizations.uninstall.before_uninstall"
# after_uninstall = "pew_customizations.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pew_customizations.utils.before_app_install"
# after_app_install = "pew_customizations.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pew_customizations.utils.before_app_uninstall"
# after_app_uninstall = "pew_customizations.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "pew_customizations.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pew_customizations.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"pew_customizations.tasks.all"
# 	],
# 	"daily": [
# 		"pew_customizations.tasks.daily"
# 	],
# 	"hourly": [
# 		"pew_customizations.tasks.hourly"
# 	],
# 	"weekly": [
# 		"pew_customizations.tasks.weekly"
# 	],
# 	"monthly": [
# 		"pew_customizations.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "pew_customizations.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "pew_customizations.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pew_customizations.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pew_customizations.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pew_customizations.utils.before_request"]
# after_request = ["pew_customizations.utils.after_request"]

# Job Events
# ----------
# before_job = ["pew_customizations.utils.before_job"]
# after_job = ["pew_customizations.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"pew_customizations.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

