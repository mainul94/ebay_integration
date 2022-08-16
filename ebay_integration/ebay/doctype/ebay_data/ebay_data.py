# Copyright (c) 2022, Mainul Islam and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ast import literal_eval
from frappe.utils.data import cstr, flt, get_datetime_str
from erpnext import get_default_company
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.setup.utils import get_exchange_rate
from erpnext.accounts.doctype.account.account import get_account_currency

class eBayData(Document):
    def on_submit(self):
        self.make_order()

    @frappe.whitelist()
    def make_order(self):
        if self.new_name or self.status in ('Open', 'Failed'):
            try:
                self._new_sales_order()
                self.db_set('new_name', self.order.name)
                status = 'Success'
            except:
                self.db_set('error', cstr(frappe.get_traceback()))
                status = 'Failed'
        self.db_set('status', status)

    def _new_sales_order(self):
        self.parsed_doc = self.parse_data()
        self.order = frappe.new_doc('Sales Order')
        self._set_customer_and_address()
        self.order.set('company', get_default_company())
        self.order.set('transaction_date', self.ebay_creation)
        self.order.set('ignore_pricing_rule', 1)
        self.order.set('delivery_date', get_datetime_str(self.parsed_doc['fulfillmentStartInstructions'][-1]['minEstimatedDeliveryDate']))
        self.order.set(
            'currency', self.parsed_doc['pricingSummary']['total']['currency'])
        if 'convertedFromCurrency' in  self.parsed_doc['paymentSummary']['totalDueSeller']\
            and self.parsed_doc['paymentSummary']['totalDueSeller']['currency'] != self.order.currency:
            self.order.set('conversion_rate', flt(self.parsed_doc['paymentSummary']['totalDueSeller']['value'])/flt(self.parsed_doc['paymentSummary']['totalDueSeller']['convertedFromValue']))
        self._set_ord_items()
        self.order.run_method("set_missing_values")
        self._add_charges()
        self.order.run_method("calculate_taxes_and_totals")
        self.order.insert()
        self.order.submit()
        # Make Payment
        if self.parsed_doc['paymentSummary']['payments'][-1]['paymentStatus']=="PAID":
            pe = get_payment_entry(self.order.doctype, self.order.name)
            pe.reference_no = self.parsed_doc['paymentSummary']['payments'][-1]['paymentReferenceId']
            pe.reference_date = get_datetime_str(self.parsed_doc['paymentSummary']['payments'][-1]['paymentDate'])
            pe.submit()
        
    def _add_charges(self):
        self.order.set('taxes', [])
        default_expense_account = frappe.db.get_value('Company', self.order.company, 'default_expense_account')
        self.order.append('taxes', {
            'charge_type': 'Actual',
            'account_head': default_expense_account,
            'description': default_expense_account,
            'tax_amount': flt(self.parsed_doc['pricingSummary']['deliveryCost']['value']) * self.order.conversion_rate,
        })

    def _set_ord_items(self):
        self.order.set('items', [])
        for row in self.parsed_doc['lineItems']:
            item_row = {}
            if not frappe.db.exists('Item', row['legacyItemId']):
                frappe.get_doc(
                    {'doctype': 'Item', 'item_code': row['legacyItemId'], 'item_name': row['title'], 'item_group': 'Products'}).insert()
            item_row['item_code'] = row['legacyItemId']
            item_row['item_name'] = row['title']
            item_row['qty'] = row['quantity']
            item_row['rate'] = flt(row['lineItemCost']['value']) / row['quantity']
            item_row['amount'] = row['lineItemCost']['value']
            item_row['additional_notes'] = f"Delivery Coset: {row['deliveryCost']['shippingCost']['value']}"
            self.order.append('items', item_row)

    def parse_data(self):
        doc = frappe._dict(literal_eval(self.data))
        return doc

    def _set_customer_and_address(self):
        cust = frappe.db.get_value(
            'Customer', {'ebay_id': self.parsed_doc['buyer']['username']})
        address = shipping_address_from_fulfillment(
            self.parsed_doc['fulfillmentStartInstructions'])
        if cust:
            self.order.set('customer', cust)
        else:
            cust = frappe.new_doc('Customer')
            cust.update({
                'ebay_id': self.parsed_doc['buyer']['username'],
                'customer_name': address.address_title if address else self.parsed_doc['buyer']['username'],
                'customer_type': 'Individual',
                'customer_group': 'Individual',
                'territory': get_territory_from_country_code(self.parsed_doc['buyer']['taxAddress']['countryCode']),
                'customer_primary_address': address.name if address else ''
            })
            cust.insert()
            self.order.set('customer', cust.name)
        if address:
            self.order.set('shipping_address', address.name)


def get_territory_from_country_code(country_code):
    country = frappe.db.get_value(
        'Country', {'code': cstr(country_code).lower()})
    if frappe.db.exists('Territory', country):
        return country
    return 'Rest Of The World'


def shipping_address_from_fulfillment(fulfilment):
    if not fulfilment:
        return {}
    address = [
        x for x in fulfilment if x['fulfillmentInstructionsType'] == 'SHIP_TO']
    address = address[0] if address else fulfilment[-1]
    country = frappe.db.get_value('Country', {'code': cstr(
        address['shippingStep']['shipTo']['contactAddress']['countryCode']).lower()})
    doc = {
        'address_title': address['shippingStep']['shipTo']['fullName'],
        'address_type': 'Shipping',
        'address_line1': address['shippingStep']['shipTo']['contactAddress']['addressLine1'],
        'city': address['shippingStep']['shipTo']['contactAddress']['city'],
        'pincode': address['shippingStep']['shipTo']['contactAddress']['postalCode'],
        'state': address['shippingStep']['shipTo']['contactAddress']['stateOrProvince'],
        'country': country
    }
    if address['shippingStep']['shipTo']['primaryPhone'].get('phoneNumber'):
        doc['phone'] = address['shippingStep']['shipTo']['primaryPhone'].get('phoneNumber')
    if frappe.db.exists('Address', doc):
        add_doc = frappe.get_doc('Address', doc)
    else:
        doc['doctype'] = 'Address'
        add_doc = frappe.get_doc(doc)
        add_doc.insert()
    return add_doc
