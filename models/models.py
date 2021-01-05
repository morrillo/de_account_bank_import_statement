# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import psycopg2

from odoo import api, models, fields
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, pycompat


import re

def change_date_format(dt):
        #return re.sub(r'(\d{4})-(\d{1,2})-(\d{1,2})', '\\3-\\2-\\1', dt)a
	# server_format = DEFAULT_SERVER_DATE_FORMAT if field['type'] == 'date' else DEFAULT_SERVER_DATETIME_FORMAT
	# '%Y-%m-%d'
	server_format = DEFAULT_SERVER_DATE_FORMAT
	server_format = server_format.replace('%Y','\\3')
	server_format = server_format.replace('%m','\\2')
	server_format = server_format.replace('%d','\\1')
	#import pdb;pdb.set_trace()
	#return re.sub(r'(\d{1,2}).(\d{1,2}).(\d{4})', '\\1-\\2-\\3', dt)
	return re.sub(r'(\d{1,2}).(\d{1,2}).(\d{4})', server_format, dt)


class AccountBankStatementImport(models.TransientModel):
    _inherit = "account.bank.statement.import"

    def _check_csv(self, filename):
        return filename and filename.lower().strip().endswith('.csv')

    @api.multi
    def import_file(self):
        if not self._check_csv(self.filename):
            return super(AccountBankStatementImport, self).import_file()
        data_txt =  base64.b64decode(self.data_file).decode('utf-8')
        date_pattern = r'([0-3][0-9][.][0-1][0-9][.][2][0][0-9][0-9])'
        x = re.findall(date_pattern, data_txt)
        match_items = []
        for item in x:
            res = change_date_format(item)
            match_items.append([item,res])
        for match_item in match_items:
            data_txt = data_txt.replace(match_item[0],match_item[1])
        #data_base64 = base64.b64encode(data_txt)

        ctx = dict(self.env.context)
        import_wizard = self.env['base_import.import'].create({
            'res_model': 'account.bank.statement.line',
            #'file': base64.b64decode(self.data_file),
            'file': data_txt.encode('ascii','ignore'),
            'file_name': self.filename,
            'file_type': 'text/csv'
        })
        ctx['wizard_id'] = import_wizard.id
        return {
            'type': 'ir.actions.client',
            'tag': 'import_bank_stmt',
            'params': {
                'model': 'account.bank.statement.line',
                'context': ctx,
                'filename': self.filename,
            }
        }




class AccountBankStatementLine(models.Model):
	_inherit = "account.bank.statement.line"

	amount_sign = fields.Char('Amount Sign')


class AccountBankStmtImportCSV(models.TransientModel):
    _inherit = 'base_import.import'


    @api.multi
    def _parse_import_data(self, data, import_fields, options):
        data = super(AccountBankStmtImportCSV, self)._parse_import_data(data, import_fields, options)
        statement_id = self._context.get('bank_statement_id', False)
        if not statement_id:
            return data
        ret_data = []

        vals = {}
        import_fields.append('statement_id/.id')
        import_fields.append('sequence')
        index_balance = False
        convert_to_amount = False
        index_amount_sign = 0
        if 'amount_sign' in import_fields:
            index_amount_sign = import_fields.index('amount_sign')
        index_amount = import_fields.index('amount')

        if index_amount_sign and index_amount:
            for i,data_line in enumerate(data):
                if data_line[index_amount_sign] == 'S':
                    line_amount = data[i][index_amount].replace('.','')
                    line_amount = data[i][index_amount].replace('.','')
                    data[i][index_amount] = str((float(line_amount) * (-1) / 100))
                else:
                    line_amount = data[i][index_amount].replace('.','')
                    line_amount = data[i][index_amount].replace('.','')
                    data[i][index_amount] = str((float(line_amount) / 100))
        else:
            for i,data_line in enumerate(data):
                line_amount = data[i][index_amount].replace('.','')
                line_amount = data[i][index_amount].replace('.','')
                data[i][index_amount] = str((float(line_amount) / 100))

        if 'debit' in import_fields and 'credit' in import_fields:
            index_debit = import_fields.index('debit')
            index_credit = import_fields.index('credit')
            self._parse_float_from_data(data, index_debit, 'debit', options)
            self._parse_float_from_data(data, index_credit, 'credit', options)
            import_fields.append('amount')
            convert_to_amount = True
        # add starting balance and ending balance to context
        if 'balance' in import_fields:
            index_balance = import_fields.index('balance')
            self._parse_float_from_data(data, index_balance, 'balance', options)
            vals['balance_start'] = self._convert_to_float(data[0][index_balance])
            vals['balance_start'] -= self._convert_to_float(data[0][import_fields.index('amount')]) \
                                            if not convert_to_amount \
                                            else abs(self._convert_to_float(data[0][index_debit]))-abs(self._convert_to_float(data[0][index_credit]))
            vals['balance_end_real'] = data[len(data)-1][index_balance]
            import_fields.remove('balance')
        # Remove debit/credit field from import_fields
        if convert_to_amount:
            import_fields.remove('debit')
            import_fields.remove('credit')

        for index, line in enumerate(data):
            line.append(statement_id)
            line.append(index)
            remove_index = []
            if convert_to_amount:
                line.append(
                    abs(self._convert_to_float(line[index_credit]))
                    - abs(self._convert_to_float(line[index_debit]))
                )
                remove_index.extend([index_debit, index_credit])
            if index_balance:
                remove_index.append(index_balance)
            # Remove added field debit/credit/balance
            for index in sorted(remove_index, reverse=True):
                line.remove(line[index])
            if line[import_fields.index('amount')]:
                ret_data.append(line)
        if 'date' in import_fields:
            vals['date'] = data[len(data)-1][import_fields.index('date')]

        # add starting balance and date if there is one set in fields
        if vals:
            self.env['account.bank.statement'].browse(statement_id).write(vals)

        return ret_data

