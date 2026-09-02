function call_with_gps(frm, method) {
	const invoke = (coords) => {
		return frm.call(method, coords || {}).then(() => frm.refresh());
	};
	if (!navigator.geolocation) {
		return invoke({});
	}
	navigator.geolocation.getCurrentPosition(
		(pos) => invoke({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
		() => invoke({}),
		{ enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
	);
}

frappe.ui.form.on("Service Job", {
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		if (status === "Draft") frm.add_custom_button(__("Schedule Job"), () => frm.call("schedule_job").then(() => frm.refresh()));
		if (["Draft", "Scheduled", "Assigned"].includes(status)) frm.add_custom_button(__("Assign Technician"), () => frm.call("assign_technician").then(() => frm.refresh()));
		if (status === "Assigned") frm.add_custom_button(__("Start Travel"), () => call_with_gps(frm, "start_travel"));
		if (status === "In Transit") frm.add_custom_button(__("Mark Arrived"), () => call_with_gps(frm, "mark_arrived"));
		if (["Arrived", "Assigned"].includes(status)) frm.add_custom_button(__("Start Work"), () => frm.call("start_work").then(() => frm.refresh()));
		if (status === "Work In Progress") {
			frm.add_custom_button(__("Add Part"), () => frm.add_child("parts") && frm.refresh_field("parts"));
			frm.add_custom_button(__("Add Labour"), () => frm.add_child("labour") && frm.refresh_field("labour"));
			frm.add_custom_button(__("Mark Awaiting Parts"), () => frm.call("mark_awaiting_parts").then(() => frm.refresh()));
			frm.add_custom_button(__("Mark Awaiting Customer"), () => frm.call("mark_awaiting_customer").then(() => frm.refresh()));
			frm.add_custom_button(__("Create Stock Entry"), () => frm.call("create_service_stock_entry").then(() => frm.refresh()));
			frm.add_custom_button(__("Complete Job"), () => call_with_gps(frm, "complete_job"));
		}
		if (["Awaiting Parts", "Awaiting Customer"].includes(status)) frm.add_custom_button(__("Resume Work"), () => frm.call("resume_work").then(() => frm.refresh()));
		if (frm.doc.po_required && frm.doc.po_status !== "Approved") {
			frm.add_custom_button(__("Approve Customer PO"), () => frm.call("approve_customer_po").then(() => frm.refresh()));
		}
		if (status === "Completed" && !frm.doc.sales_invoice && !frm.doc.service_billing_batch) {
			frm.add_custom_button(__("Create Invoice"), () => {
				frm.call("create_sales_invoice").then((r) => {
					if (r.message) frappe.set_route("Form", "Sales Invoice", r.message);
				});
			});
		}
		frm.add_custom_button(__("Calculate Billing"), () => frm.call("calculate_billing").then(() => frm.refresh()));
		frm.add_custom_button(__("Re-evaluate Coverage"), () => frm.call("reevaluate_coverage").then(() => frm.refresh()));
	},
});
