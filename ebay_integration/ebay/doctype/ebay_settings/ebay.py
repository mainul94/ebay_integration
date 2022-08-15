import frappe
from frappe.model.document import Document
from frappe.utils.data import cstr, get_datetime_str
from requests import session
from frappe.core.page.background_jobs.background_jobs import get_info


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
        elif 500 > r.status_code >=400  and not self.retry:
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
        # params = {
        #     'filter':{
        #         'orderfulfillmentstatus':'{NOT_STARTED|IN_PROGRESS}'
        #     }
        # }
        params=None
        lastmodifieddate = frappe.db.get_value('eBay Data', fieldname='max(ebay_modified)')
        if lastmodifieddate:
            # params['filter']['lastmodifieddate'] = f'[{lastmodifieddate.isoformat()}..]'
            params = {
                'filter':{
                    'lastmodifieddate': f'[{lastmodifieddate.isoformat()}..]'
                }
            }
        data = self._request('GET', url, params=params)
        self.order_data_process(data)
    
    def order_data_process(self, data):
        if not data:
            return
        # Process.
        for row in data.get('orders') or []:
            if frappe.db.exists('eBay Data', {'ebay_id': row['orderId'], 'ebay_modified': get_datetime_str(row['lastModifiedDate'])}):
                continue
            doc = frappe.new_doc('eBay Data')
            doc.update({
                'ebay_id': row['orderId'],
                'ebay_creation': get_datetime_str(row['creationDate']),
                'ebay_modified': get_datetime_str(row['lastModifiedDate']),
                'data': cstr(row)
            })
            doc.insert()
        # Load Next Page Data
        if data.get('next'):
            new_data = self._request('GET', data.get('next'))
            self.order_data_process(new_data)


def schedule_pull_order():
    job_name='eBayOrderPulling'
    if any(x['job_name'] == job_name for x in get_info() if x['status'] in ('started', 'queued')):
        # Already another job running for this.
        return
    frappe.enqueue('ebay_integration.ebay.doctype.ebay_settings.ebay._pull_order', timeout=600, job_name=job_name)

def _pull_order():
    settings = frappe.get_cached_doc('eBay Settings', 'eBay Settings')
    ebay = eBayConnector(settings)
    ebay.get_orders()
