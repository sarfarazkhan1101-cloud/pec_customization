// "Client Site Visit" checkbox on the Frappe HR PWA check-in sheet.
//
// Added to /hrms by pew_customizations.hr.pwa (an after_request hook); no HRMS file is changed.
// Ticking the box takes a fresh GPS reading, and that one Employee Checkin insert is sent with
// pew_client_site_visit = 1 and that reading. The server (pew_customizations.hr.employee_checkin)
// then skips only the office radius check. If this script cannot find the sheet after an HRMS
// update, nothing is shown and the standard office check applies.
//
// Plain ES2015: this file is served as is, without the build step that transpiles the PWA.
(function () {
	const SHEET_TRIGGER = "open-checkin-modal"; // id of the PWA button that opens the check-in sheet
	const INSERT_PATH = "/api/method/frappe.client.insert";
	const FIELD = "pew_client_site_visit";

	// The open sheet's state. A new sheet (or a closed one) starts unticked.
	let visit = newVisit(null);

	function newVisit(root) {
		return { root: root, checked: false, location: null, result: null };
	}

	function __(text) {
		const messages = window.frappe && window.frappe.boot && window.frappe.boot.__messages;
		return (messages && messages[text]) || text;
	}

	function findSheet() {
		const modals = document.querySelectorAll("ion-modal");
		for (let i = 0; i < modals.length; i++) {
			const modal = modals[i];
			if (
				modal.trigger === SHEET_TRIGGER ||
				modal.getAttribute("trigger") === SHEET_TRIGGER
			) {
				return modal;
			}
		}
		return null;
	}

	// Put the checkbox above the sheet's Confirm button (its last button).
	function sync() {
		const sheet = findSheet();
		if (!sheet) return;
		const buttons = sheet.querySelectorAll("button");
		const confirm = buttons[buttons.length - 1];
		if (!confirm || !confirm.parentNode) return;

		if (visit.root !== confirm.parentNode) visit = newVisit(confirm.parentNode);
		if (!visit.root.querySelector(".pew-client-site"))
			visit.root.insertBefore(render(), confirm);
	}

	function render() {
		const box = document.createElement("div");
		box.className = "pew-client-site";
		box.style.cssText = "width:100%;display:flex;flex-direction:column;gap:4px";
		box.innerHTML =
			'<label style="display:flex;align-items:center;gap:10px;font-size:15px;font-weight:500;color:#171717">' +
			'<input type="checkbox" style="width:18px;height:18px;margin:0;accent-color:#171717">' +
			"<span></span></label>" +
			'<div class="pew-client-site-status" style="font-size:13px;color:#7c7c7c"></div>';
		box.querySelector("span").textContent = __("Client Site Visit");

		const input = box.querySelector("input");
		input.checked = visit.checked;
		input.addEventListener("change", () => {
			visit.checked = input.checked;
			if (input.checked) {
				readLocation();
			} else {
				visit.location = visit.result = null;
			}
			showStatus();
		});
		setTimeout(showStatus);
		return box;
	}

	function showStatus() {
		const status = visit.root && visit.root.querySelector(".pew-client-site-status");
		if (!status) return;
		const result = visit.result;
		if (!visit.checked) {
			status.textContent = "";
		} else if (!result) {
			status.textContent = __("Getting your current location...");
		} else if (result.error) {
			status.textContent = __("Location unavailable") + ": " + result.error;
		} else {
			status.textContent =
				__("Location captured") + " (±" + Math.round(result.accuracy) + " m)";
		}
	}

	// A fresh reading, never a cached one: the PWA keeps its last coordinates when a later reading
	// fails, which would place a client visit at the office.
	function readLocation() {
		const location = new Promise((resolve) => {
			if (!navigator.geolocation) {
				resolve({ error: __("Geolocation is not supported by your current browser") });
				return;
			}
			navigator.geolocation.getCurrentPosition(
				(position) =>
					resolve({
						latitude: position.coords.latitude,
						longitude: position.coords.longitude,
						accuracy: position.coords.accuracy,
					}),
				(error) =>
					resolve({ error: error.message || __("Unable to retrieve your location") }),
				{ enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
			);
		});
		visit.location = location;
		visit.result = null;
		location.then((result) => {
			if (visit.location !== location) return;
			visit.result = result;
			showStatus();
		});
		return location;
	}

	// The parsed body of an Employee Checkin insert, else null.
	function checkinInsert(input, init) {
		try {
			const url = typeof input === "string" ? input : input.url;
			if (new URL(url, location.origin).pathname !== INSERT_PATH) return null;
			if (!init || typeof init.body !== "string") return null;
			const body = JSON.parse(init.body);
			return body && body.doc && body.doc.doctype === "Employee Checkin" ? body : null;
		} catch (e) {
			return null;
		}
	}

	const nativeFetch = window.fetch;
	window.fetch = function (input, init) {
		const body = visit.checked ? checkinInsert(input, init) : null;
		if (!body) return nativeFetch.apply(window, arguments);

		// retry a reading that failed, e.g. after the employee allowed location access
		const location =
			!visit.location || (visit.result && visit.result.error)
				? readLocation()
				: visit.location;
		showStatus();
		return location.then((result) => {
			body.doc[FIELD] = 1;
			// no reading: 0, 0, which the server refuses with a clear message
			body.doc.latitude = result.error ? 0 : result.latitude;
			body.doc.longitude = result.error ? 0 : result.longitude;
			return nativeFetch.call(
				window,
				input,
				Object.assign({}, init, { body: JSON.stringify(body) })
			);
		});
	};

	// A closed sheet starts unticked when opened again, whether or not Ionic kept its content.
	document.addEventListener("ionModalDidDismiss", (event) => {
		if (event.target !== findSheet()) return;
		event.target.querySelectorAll(".pew-client-site").forEach((box) => box.remove());
		visit = newVisit(null);
	});

	let queued = false;
	new MutationObserver(() => {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			sync();
		});
	}).observe(document.body, { childList: true, subtree: true });
})();
