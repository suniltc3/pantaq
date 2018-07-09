# -*- coding: utf-8 -*-


import werkzeug

from odoo import fields, http, _, SUPERUSER_ID
from odoo.http import request
from odoo.addons.portal.controllers.mail import _message_post_helper

class sale_quote(http.Controller):

    # Overridden: website_quote
    @http.route(['/quote/accept'], type='json', auth="public", website=True)
    def accept(self, order_id, token=None, signer=None, sign=None, **post):

        order_obj = request.registry.get('sale.order')
        order = order_obj.browse(request.cr, SUPERUSER_ID, order_id)

        if token != order.access_token:
            return request.website.render('website.404')
        if order.require_payment:
            return request.website.render('website.404')
        if order.state != 'sent':
            return False

        attachments=sign and [('signature.png', sign.decode('base64'))] or []

        ctx = dict(request.context)
        ctx['websiteQuote'] = True
        order_obj.action_confirm_quote(request.cr, SUPERUSER_ID, [order_id], context=ctx)

        message = _('Order signed by %s') % (signer,)
        _message_post_helper(message=message, res_id=order_id, res_model='sale.order', attachments=attachments, **({'token': token, 'token_field': 'access_token'} if token else {}))

        try:
            messageIQ = _('Quotation is accepted by the Customer')
            order.intorder_id.sudo().message_post(body = messageIQ)
            order.intorder_id.sudo().action_done()
        except:
            pass

        return True


    # Overridden: website_quote
    @http.route(['/quote/<int:order_id>/<token>/decline'], type='http', auth="public", methods=['POST'], website=True)
    def decline(self, order_id, token, **post):
        print ("decline ****")
        ctx = dict(self._context)
        order_obj = request.registry.get('sale.order')
        order = order_obj.browse(request.cr, SUPERUSER_ID, order_id)
        if token != order.access_token:
            return request.website.render('website.404')
        if order.state != 'sent':
            return werkzeug.utils.redirect("/quote/%s/%s?message=4" % (order_id, token))
        request.registry.get('sale.order').action_cancel(request.cr, SUPERUSER_ID, [order_id])
        message = post.get('decline_message')
        if message:
            _message_post_helper(message=message, res_id=order_id, res_model='sale.order', **{'token': token, 'token_field': 'access_token'} if token else {})

        try:
            messageIQ = _('Quotation is rejected by the Customer')
            order.intorder_id.sudo().message_post(body = messageIQ)
            ctx.update({'websiteCall' : True})
            order.intorder_id.sudo().with_context().action_rejected()
        except:
            pass

        return werkzeug.utils.redirect("/quote/%s/%s?message=2" % (order_id, token))

    @http.route(['/quote/update_line'], type='json', auth="public", website=True)
    def update(self, line_id, remove=False, unlink=False, reject=False, revise=False, reset=False, order_id=None, token=None, **post):
        res = False
        order = request.registry.get('sale.order').browse(request.cr, SUPERUSER_ID, int(order_id))
        if token != order.access_token:
            return request.website.render('website.404')
        if order.state not in ('draft','sent'):
            return False

        line_id = int(line_id)
        itemState = False

        if unlink:
            request.registry.get('sale.order.line').unlink(request.cr, SUPERUSER_ID, [line_id], context=request.context)
            return False

        order_line_obj = request.registry.get('sale.order.line')
        order_line_val = order_line_obj.read(request.cr, SUPERUSER_ID, [line_id], [], context=request.context)[0]
        quantity = order_line_val['product_uom_qty']

        vals = {}
        if reject or revise or reset:
            if reject: itemState = 'cancel'
            elif revise: itemState = 'revise'
            else: itemState = False
            # vals.update({'item_state': itemState})
        else:
            number = (remove and -1 or 1)
            quantity += number
            # vals.update({'product_uom_qty': (quantity)})
            # TODO:
            #   need to check thoroughly
            res = [str(quantity), str(order.amount_total)]

        order_line_obj.write(request.cr, SUPERUSER_ID, [line_id], vals, context=request.context)
        return res

