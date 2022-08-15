# Copyright (c) 2022, Mainul Islam and contributors
# For license information, please see license.txt

import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils.data import add_to_date, get_url, now_datetime, cint, cstr
from frappe.utils.response import Response
import requests
import base64
import urllib
from frappe import _


class eBaySettings(Document):
    @frappe.whitelist()
    def get_gant_url(self):
        url = f"https://auth.{'sandbox.' if self.sandbox else ''}ebay.com/oauth2/authorize?"
        frappe.cache().set_value('ebay_gant_state',
                                 frappe.generate_hash(length=16), expires_in_sec=600)
        data = {
            'client_id': self.client_id,
            'redirect_uri': self.ru_name,
            'response_type': 'code',
            'state': frappe.cache().get_value('ebay_gant_state'),
            'scope': ' '.join(self.scope.split('\n'))
        }
        url += urllib.parse.urlencode(data)
        return url
    
    def get_oauth_code(self):
        pass
        #TODO: In Future

    def get_oauth_code_by_refresh_code(self):
        url, headers = self.get_url_headers()
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'scope': ' '.join(self.scope.split('\n'))
        }
        r = requests.request('POST', url, data=data, headers=headers)
        if r.status_code == 200:
            self.db_set('access_token', r.json()['access_token'])

    def get_exchanges_token(self):
        url, headers = self.get_url_headers()
        data = {
            'grant_type': 'authorization_code',
            'code': self.access_token,
            'redirect_uri': self.ru_name
        }
        r = requests.request('POST', url, data=data, headers=headers)
        if r.status_code == 200:
            update_ebay_settings(frappe._dict(r.json()))
    
    def get_url_headers(self):
        url = f"https://api.{'sandbox.' if self.sandbox else ''}ebay.com/identity/v1/oauth2/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': "Basic {}".format(cstr(base64.b64encode(f"{self.client_id}:{self.get_password('client_secret')}".encode())))
        }
        return url, headers


@frappe.whitelist(allow_guest=True, methods=['GET'])
def verify_ebay_marketplace(**kwargs):
    from_ditct = frappe.form_dict
    challengeCode = from_ditct.challenge_code
    if challengeCode:
        verificationToken = frappe.conf.get('ebay_verification_token')
        endpoint = get_url(
            'api/method/ebay_integration.ebay.doctype.ebay_settings.ebay_settings.verify_ebay_marketplace', full_address=True)
        response_code = hashlib.sha256(
            (challengeCode+verificationToken+endpoint).encode())
        res = {
            "challengeResponse": response_code.hexdigest()
        }
        return Response(frappe.as_json(res), 200, content_type='application/json')
    return True


@frappe.whitelist()
def oauth_accept(**kwargs):
    if kwargs.get('code') and kwargs.get('state') == frappe.cache().get_value('ebay_gant_state'):
        frappe.db.set_value('eBay Settings', None,
                            'access_token', kwargs.get('code'))
        settings = frappe.get_single('eBay Settings')
        settings.db_set('access_token', kwargs.get('code'))
        settings.get_exchanges_token()
        frappe.db.commit()
        return frappe.respond_as_web_page(_("Success"), '<h2>Successfully Sotore your code.</h2>')
    return frappe.respond_as_web_page(_("Ops"), '<h2>Something giong to wroing please contact with Suppoet.</h2>', "Ops", 403)


@frappe.whitelist()
def oauth_decline(**kwargs):
    frappe.respond_as_web_page(_("Sorry"), '<h2>Sorry you diclent given access.</h2>', False, 403)


def update_ebay_settings(data):
    settings = frappe.get_single('eBay Settings')
    settings.db_set('access_token', data.get('access_token'))
    settings.db_set('refresh_token', data.get('refresh_token'))
    if data.get('refresh_token_expires_in'):
        settings.db_set('refresh_token_expired_at', add_to_date(
            now_datetime(), seconds=cint(data.get('refresh_token_expires_in'))-20))

@frappe.whitelist()
def get_gant_url():
    return frappe.get_cached_doc('eBay Settings', 'eBay Settings').get_gant_url()
