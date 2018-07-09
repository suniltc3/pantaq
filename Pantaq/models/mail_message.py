

from email.utils import formataddr

from odoo import _, api, fields, models, SUPERUSER_ID




class pq_mail_message(models.Model):
    """ Replicates Messages model: stores unattended incoming emails.
                        (Emails failed to find its Source Records)
    """
    _name = 'pq.mail.message'
    _description = 'PQ Mail Message'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _rec_name = 'record_name'

    _message_read_limit = 30

    @api.model
    def _get_default_from(self):
        if self.env.user.alias_name and self.env.user.alias_domain:
            return formataddr((self.env.user.name, '%s@%s' % (self.env.user.alias_name, self.env.user.alias_domain)))
        elif self.env.user.email:
            return formataddr((self.env.user.name, self.env.user.email))
        raise UserError(_("Unable to send email, please configure the sender's email address or alias."))

    @api.model
    def _get_default_author(self):
        return self.env.user.partner_id

    # content
    subject = fields.Char('Subject')
    date = fields.Datetime('Date', default=fields.Datetime.now)
    body = fields.Html('Contents', default='', help='Automatically sanitized HTML contents')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'pq_message_attachment_rel',
        'message_id', 'attachment_id',
        string='Attachments',
        help='Attachments are linked to a document through model / res_id and to the message'
             'through this field.')
    # parent_id = fields.Many2one(
    #     'pq.mail.message', 'Parent Message', select=True, ondelete='set null',
    #     help="Initial thread message.")
    # child_ids = fields.One2many('pq.mail.message', 'parent_id', 'Child Messages')

    # related document
    model = fields.Char('Related Document Model', index=1)
    res_id = fields.Integer('Related Document ID', index=1)
    record_name = fields.Char('Message Record Name', help="Name get of the related document.")
    # characteristics
    message_type = fields.Selection([
        ('email', 'Email'),
        ('comment', 'Comment'),
        ('notification', 'System notification')],
        string='Type', required=True, default='email',
        help="Message type: email for email message, notification for system "
             "message, comment for other messages such as user replies")
    subtype_id = fields.Many2one('mail.message.subtype', 'Subtype', ondelete='set null', index=1)

    # origin
    email_from = fields.Char(
        'From', default=_get_default_from,
        help="Email address of the sender. This field is set when no matching partner is found and replaces the author_id field in the chatter.")
    author_id = fields.Many2one(
        'res.partner', 'Author', index=1,
        ondelete='set null', default=_get_default_author,
        help="Author of the message. If not set, email_from may hold an email address that did not match any partner.")
    author_avatar = fields.Binary("Author's avatar", related='author_id.image_small')

    # recipients
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    # needaction_partner_ids = fields.Many2many(
    #     'res.partner', 'mail_message_res_partner_needaction_rel', string='Partners with Need Action')
    # needaction = fields.Boolean(
    #     'Need Action', compute='_get_needaction', search='_search_needaction',
    #     help='Need Action')
    # channel_ids = fields.Many2many(
    #     'mail.channel', 'mail_message_mail_channel_rel', string='Channels')
    # user interface
    # starred_partner_ids = fields.Many2many(
    #     'res.partner', 'mail_message_res_partner_starred_rel', string='Favorited By')
    # starred = fields.Boolean(
    #     'Starred', compute='_get_starred', search='_search_starred',
    #     help='Current user has a starred notification linked to this message')

    # # tracking
    # tracking_value_ids = fields.One2many(
    #     'mail.tracking.value', 'mail_message_id',
    #     string='Tracking values',
    #     help='Tracked values are stored in a separate model. This field allow to reconstruct'
    #          'the tracking and to generate statistics on the model.')

    # mail gateway
    no_auto_thread = fields.Boolean(
        'No threading for answers',
        help='Answers do not go in the original document discussion thread. This has an impact on the generated message-id.')
    message_id = fields.Char('Message-Id', help='Message unique identifier', index=1, readonly=1, copy=False)
    reply_to = fields.Char('Reply-To', help='Reply email address. Setting the reply_to bypasses the automatic thread creation.')
    mail_server_id = fields.Many2one('ir.mail_server', 'Outgoing mail server')
