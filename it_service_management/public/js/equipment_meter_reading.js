frappe.ui.form.on("Equipment Meter Reading", {
	refresh(frm) {
		if (!frm.is_new() || (frm.doc.details || []).length) return;
		["BW", "COLOUR"].forEach((meter_type) => {
			const row = frm.add_child("details");
			row.meter_type = meter_type;
		});
		frm.refresh_field("details");
	},
});
