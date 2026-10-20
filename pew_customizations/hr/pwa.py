"""Adds the Client Site Visit checkbox to the Frappe HR PWA (/hrms).

The PWA is a prebuilt Vue bundle with no extension points, so instead of changing HRMS, an
`after_request` hook adds one <script> tag to the page's HTML. The script (public/js/
hrms_client_site_visit.js) only shows the checkbox and sends the flag; what the flag allows is decided
on the server (hr/employee_checkin.py). If an HRMS update changes the check-in sheet so the script
cannot find it, the checkbox is simply not shown and the office radius keeps applying.
"""

import os

import frappe

SCRIPT = "js/hrms_client_site_visit.js"


def add_client_site_script(response=None, request=None):
	if not (response and request) or (request.path != "/hrms" and not request.path.startswith("/hrms/")):
		return
	if response.status_code != 200 or response.mimetype != "text/html" or response.direct_passthrough:
		return

	html = response.get_data(as_text=True)
	if SCRIPT in html or "</body>" not in html:
		return
	head, body_end, tail = html.rpartition("</body>")
	response.set_data(f"{head}{_script_tag()}\n{body_end}{tail}")


def _script_tag():
	# the file's mtime changes with each deploy that changes it, so browsers and nginx fetch it again
	version = int(os.path.getmtime(frappe.get_app_path("pew_customizations", "public", SCRIPT)))
	return f'<script src="/assets/pew_customizations/{SCRIPT}?v={version}"></script>'
