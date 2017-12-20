# -*- coding: utf-8 -*-

from odoo import api, models, fields

class StockMoveLine(models.Model):
    _inherit = "stock.move.line"


    @api.multi
    def _prepare_info(self):
        """
            Prepares the following info of the move line self:
            - id: int
            - create_date: datetime
            - location_dest_id: {stock.lcation}
            - location_id: {stock.lcation}
            - lot_id: TBC
            - package_id: {stock.quant.package}
            - qty_done: float
            - result_package_id: {stock.quant.package}
            - write_date: datetime
        """
        self.ensure_one()

        return {"id": self.id,
                "create_date": self.create_date,
                "location_id": self.location_id.get_info()[0],
                "location_dest_id": self.location_dest_id.get_info()[0],
                #"lot_id": self.lot_id.id,
                "package_id": self.package_id.get_info()[0],
                "result_package_id": self.result_package_id.get_info()[0],
                "qty_done": self.qty_done,
                "write_date": self.write_date,
               }

    @api.multi
    def get_info(self):
        """ Return a list with the information of each move line in self.
        """
        res = []
        for line in self:
            res.append(line._prepare_info())

        return res