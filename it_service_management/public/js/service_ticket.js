frappe.ui.form.on("Service Ticket", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Create Service Job"), () => {
				frm.call("create_service_job").then((r) => {
					if (r.message) frappe.set_route("Form", "Service Job", r.message);
				});
			});
			if (["Open", "Assigned", "Remote Support", "Onsite Required", "Scheduled", "Awaiting Customer", "Awaiting Parts", "Work In Progress", "Resolved"].includes(frm.doc.status)) {
				frm.add_custom_button(__("Re-evaluate Coverage"), () => frm.call("reevaluate_coverage").then(() => frm.refresh()));
			}
			if (frm.doc.status === "Resolved") {
				frm.add_custom_button(__("Close Ticket"), () => frm.call("close_ticket").then(() => frm.refresh()));
				frm.add_custom_button(__("Create Knowledge Article"), () => {
					frm.call("create_knowledge_article").then((r) => {
						if (r.message) frappe.set_route("Form", "ITSM Knowledge Article", r.message);
					});
				});
			}
			if (frm.doc.ticket_type === "Incident") {
				frm.add_custom_button(__("Create Problem"), () => {
					frm.call("create_problem").then((r) => {
						if (r.message) frappe.set_route("Form", "ITSM Problem", r.message);
					});
				}, __("ITSM"));
				frm.add_custom_button(__("Declare Major Incident"), () => {
					frm.call("declare_major_incident").then((r) => {
						if (r.message) frappe.set_route("Form", "Major Incident", r.message);
					});
				}, __("ITSM"));
			}
		}
	},
	impact(frm) {
		frm.trigger("show_priority_hint");
	},
	urgency(frm) {
		frm.trigger("show_priority_hint");
	},
	show_priority_hint(frm) {
		if (frm.doc.impact && frm.doc.urgency && !frm.doc.override_reason) {
			frm.dashboard.set_headline(__("Priority is calculated server-side from Impact and Urgency on save."));
		}
	},
	customer_equipment(frm) {
		if (!frm.doc.customer_equipment) return;
		frappe.db.get_doc("Customer Equipment", frm.doc.customer_equipment).then((equipment) => {
			if (!frm.doc.customer) frm.set_value("customer", equipment.customer);
			frm.set_value("customer_site", equipment.customer_site);
			frm.set_value("item_code", equipment.item_code);
			frm.set_value("item_name", equipment.item_name);
			frm.set_value("serial_no", equipment.serial_no);
			frm.set_value("asset", equipment.asset);
			frm.set_value("service_contract", equipment.service_contract);
		});
	},
});
