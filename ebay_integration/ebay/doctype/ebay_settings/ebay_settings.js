// Copyright (c) 2022, Mainul Islam and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Settings', {
	gant_access: frm => {
		frappe.xcall('ebay_integration.ebay.doctype.ebay_settings.ebay_settings.get_gant_url').then(r=>{
			window.open(r, '_blank')
		})
	}
});
