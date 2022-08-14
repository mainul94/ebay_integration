import frappe
from frappe.model.document import Document
from requests import session


class eBayConnector():
    def __init__(self, settings) -> None:
        if not isinstance(settings, Document):
            settings = frappe.get_doc(settings)
        self.conf = settings
        self.retry = False
        self.init_session()

    def __exit__(self):
        self.req.close()
    
    ENDPOINT ={
        'get_orders': 'sell/fulfillment/v1/order',
        'get_order': 'sell/fulfillment/v1/order/{orderId}'
    }
    
    @property
    def base_url(self):
        return f"https://api.{'sandbox.' if self.conf.sandbox else ''}ebay.com/"

    def init_session(self):
        self.req = session()
        self.req.headers.update({
            'Authorization': f'Bearer {self.conf.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

    def _request(self, method, url, data=None, params=None, headers=None):
        r = self.req.request(method=method, url=url, headers=headers, json=data, params=params)
        if r.status_code==200:
            return r.json()
        elif 400 <= r.status_code >500  and not self.retry:
            self.retry = True
            self.conf.get_oauth_code_by_refresh_code()
            self.req.headers.update({
                'Authorization': f'Bearer {self.conf.access_token}'
            })
            self._request(method=method, url=url, data=data, params=params, headers=headers)
        else:
            return None

    def get_orders(self):
        url = self.base_url+self.ENDPOINT['get_orders']
        return self._request('GET', url)
