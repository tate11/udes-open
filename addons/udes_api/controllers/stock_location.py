# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from .main import UdesApi
from odoo.exceptions import ValidationError

class Location(UdesApi):

    @http.route('/api/stock-location/', type='json', methods=['GET'], auth='user')
    def get_location(self, location_id=None, location_name=None, location_barcode=None, load_quants=False, check_blocked=False):
        """ Search for a location by id, name or barcode and returns a
            stock.location object that match the given criteria.

            @param (optional) location_id
                The location's id
            @param (optional) location_name
                This is a string that entirely matches the name
            @param (optional) location_barcode
                This is a string that entirely matches the barcode
            @param (optional) load_quants: Boolean (default = false)
                Load the quants associated with a location.
            @param (optional) check_blocked:  Boolean (default = false)
                When enabled, checks if the location is blocked, in which case
                an error will be raise.
        """
        Location = request.env['stock.location']
        identifier = location_id or location_name or location_barcode
        if not identifier:
            raise ValidationError(_('You need to provide an id, name or barcode for the location.'))

        location = Location.get_location(identifier)

        if check_blocked:
            location.check_blocked()

        return location.get_info(extended=True, load_quants=load_quants)[0]
