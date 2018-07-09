# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Pantaq - Upgraded',
    'version' : '1.1',
    'summary': 'Module created for Pantaq to handle Procurement process',
    'sequence': 55,
    'author': 'Systems Valley Ltd.,',
    'description': """
Pantaq
====================
Handles Logistics and Supply Chain process to aid Procurement specialists,
who help companies achieve substantial cost savings on any area of spend.


    """,

    'category' : 'Logistics and Supply Chain',
    'website': 'https://www.pantaq.com',
    'depends' : ['crm','purchase', 'sale', 'website_quote', 'hr', 'delivery', 'account'],
    'data': [

        'data/default_config_view.xml',
        # 'data/data_workflow.xml',
        'data/email_templates.xml',

        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/mail_message_view.xml',

        'wizard/wizard_view.xml',

        'views/config_view.xml',
        'views/crm_view.xml',
        'views/purchase_view.xml',
        'views/internalQtn_view.xml',
        'views/sale_view.xml',
        'views/invoice_view.xml',

        'views/product_view.xml',

        # 'report/report_common.xml',
        'report/report_purchasequotation.xml',
        'report/report_purchaseorder.xml',
        'report/report_sales.xml',
        # 'report/report_invoice.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence':1,
}
