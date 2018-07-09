
# import mechanize
import re
import datetime
import sys
from odoo.http import request

# from xero.auth import PublicCredentials
from xero.auth import PrivateCredentials
from xero import Xero
import logging

_logger = logging.getLogger(__name__)


class MyXero(object):
    def __init__(self):
        self._credentials = False

    def getCredentials(self, Renew=False):
        # Path = '/home/deepav/Desktop/privatekey.pem'
        # ConsumerKey = 'VNUIOH588GCAH6JMJVQXSEVTICLEU5'

        Config = request.env["ir.config_parameter"]
        Path = Config.sudo().get_param('xero.pem.path')
        ConsumerKey = Config.sudo().get_param('xero.consumer.key', default='')

        if Path == '/':
            _logger.warning('Xero Credentials Not Found: Pem file path missing !!')
            return False

        if ConsumerKey == '/':
            _logger.warning('Xero Credentials Not Found: Consumer Key missing !!')
            return False

        if Renew or not self._credentials:
            rsa_key = ''
            with open(Path) as keyfile:
                rsa_key = keyfile.read()

            credentials = PrivateCredentials(ConsumerKey, rsa_key)
            self._credentials = credentials
        else:
            credentials = self._credentials

        xero = False
        try:
            xero = Xero(credentials)
        except:
            e = sys.exc_info()[1]
            _logger.warning('Xero Credentials: %s'%(str(e)))

        return xero


    def getContacts(self, LastRun=False, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID:
                result = xero.contacts.get(RecordID)

            elif LastRun:
                result = xero.contacts.filter(since=LastRun)

            else:
                result = xero.contacts.all()

        except:
            e = sys.exc_info()[1]
            log = 'Contacts: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getContacts(LastRun, RecordID, Renew=True)

        return result, log, eflag

    def putContacts(self, NewData={}, SaveData={}, Renew=False):
        if not NewData and not SaveData:
            return {}, 'Nothing to Export', False

        xero = self.getCredentials(Renew)
        log = 'Exported Successfully'
        eflag = False
        oxMapIds = {}

        try:
            # Create:
            for k, v in NewData.iteritems():
                con = xero.contacts.put(v)[0]
                oxMapIds[k] = con.get('ContactID', '')

            # Update: Existing
            writeVals = []
            for k, v in SaveData.iteritems():
                res = xero.contacts.get(k)[0]
                res.update(v)
                writeVals.append(res)

            if writeVals:
                xero.contacts.save(writeVals)

        except:
            e = sys.exc_info()[1]
            log = 'Contacts: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.putContacts(NewData, SaveData, Renew=True)

        return oxMapIds, log, eflag



    def getInvoices(self, LastRun=False, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID:
                result = xero.invoices.get(RecordID)

            elif LastRun:
                result = xero.invoices.filter(since=LastRun)
            else:
                result = xero.invoices.all()

        except:
            e = sys.exc_info()[1]
            log = 'Invoice: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getInvoices(LastRun, RecordID, Renew=True)

        return result, log, eflag

    def putInvoices(self, NewData={}, Renew=False):
        if not NewData:
            return {}, 'Nothing to Export', False

        xero = self.getCredentials(Renew)
        log = 'Exported Successfully'
        eflag = False
        oxMapIds = {}

        try:
            # Create:
            for k, v in NewData.iteritems():
                rec = xero.invoices.put(v)[0]
                oxMapIds[k] = {'id_xero': rec.get('InvoiceID', ''),
                               'number': rec.get('InvoiceNumber', ''),}

        except:
            e = sys.exc_info()[1]
            log = 'Invoice: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.putContacts(NewData, Renew=True)

        return oxMapIds, log, eflag


    def getProducts(self, LastRun=False, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID:
                result = xero.items.get(RecordID)

            elif LastRun:
                result = xero.items.filter(since=LastRun)

            else:
                result = xero.items.all()

        except:
            e = sys.exc_info()[1]
            log = 'Products: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getProducts(LastRun, RecordID, Renew=True)

        return result, log, eflag

    def putProducts(self, NewData={}, SaveData={}, Renew=False):
        if not NewData and not SaveData:
            return {}, 'Nothing to Export', False

        xero = self.getCredentials(Renew)
        log = 'Exported Successfully'
        eflag = False
        oxMapIds = {}

        try:
            # Create:
            for k, v in NewData.iteritems():
                prod = xero.items.put(v)[0]
                oxMapIds[k] = prod.get('ItemID', '')

            # Update: Existing
            writeVals = []
            for k, v in SaveData.iteritems():
                res = xero.items.get(k)[0]
                res.update(v)
                writeVals.append(res)

            if writeVals:
                xero.items.save(writeVals)

        except:
            e = sys.exc_info()[1]
            log = 'Products: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.putProducts(NewData, SaveData, Renew=True)

        return oxMapIds, log, eflag


    def getAccounts(self, LastRun=False, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID: # RecordID or Code
                result = xero.accounts.get(RecordID)

            elif LastRun:
                result = xero.accounts.filter(since=LastRun)

            else:
                result = xero.accounts.all()

        except:
            e = sys.exc_info()[1]
            log = 'Accounts: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getAccounts(LastRun, RecordID, Renew=True)

        return result, log, eflag

    def getTaxes(self, LastRun=False, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID:
                result = xero.taxrates.get(RecordID)

            elif LastRun:
                result = xero.taxrates.filter(since=LastRun)

            else:
                result = xero.taxrates.all()

        except:
            e = sys.exc_info()[1]
            log = 'Taxes: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getTaxes(LastRun, RecordID, Renew=True)

        return result, log, eflag


    def getPayments(self, LastRun=False, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID:
                result = xero.payments.get(RecordID)

            elif LastRun:
                result = xero.payments.filter(since=LastRun)

            else:
                result = xero.payments.all()

        except:
            e = sys.exc_info()[1]
            log = 'Payments: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getPayments(LastRun, RecordID, Renew=True)

        return result, log, eflag


    def getCreditNotes(self, RecordID=False, Renew=False):
        xero = self.getCredentials(Renew)
        result = []
        log = 'Imported Successfully'
        eflag = False

        try:
            if RecordID:
                result = xero.creditnotes.get(RecordID)

        except:
            e = sys.exc_info()[1]
            log = 'Credit Notes: %s'%(str(e))
            eflag = True

            if re.findall("'bool' object has no attribute", str(e)) :
                return self.getCreditNotes(RecordID, Renew=True)

        return result, log, eflag


# TODO:
# Log file
# Check life of crendentials
# Log out