# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


# Map move state to the refactor stage.
STAGES = {
    'confirmed': 'confirm',
    'waiting': 'confirm',
    'assigned': 'assign',
    'partially_available': 'assign',
    'done': 'validate'
}

class StockMove(models.Model):
    _inherit = "stock.move"

    u_grouping_key = fields.Char('Key', compute='compute_grouping_key')

    def _unreserve_initial_demand(self, new_move):
        """ Override stock default function to keep the old move lines,
            so there is no need to create them again
        """
        self.mapped('move_line_ids')\
            .filtered(lambda x: x.qty_done == 0.0)\
            .write({'move_id': new_move, 'product_uom_qty': 0})

    def _prepare_info(self):
        """
            Prepares the following info of the move in self:
            - id: int
            - location_dest_id:  {stock.location}
            - location_id: {stock.location}
            - ordered_qty: float
            - product_id: {product.product}
            - product_qty: float
            - quantity_done: float
            - move_line_ids: [{stock.move.line}]
        """
        self.ensure_one()

        return {"id": self.id,
                "location_id": self.location_id.get_info()[0],
                "location_dest_id": self.location_dest_id.get_info()[0],
                "ordered_qty": self.ordered_qty,
                "product_qty": self.product_qty,
                "quantity_done": self.quantity_done,
                "product_id": self.product_id.get_info()[0],
                "moves_line_ids": self.move_line_ids.get_info(),
               }

    def get_info(self):
        """ Return a list with the information of each move in self.
        """
        res = []
        for move in self:
            res.append(move._prepare_info())

        return res

    def compute_grouping_key(self):

        # TODO MTC: This can be refactored and abstracted at some point with
        # this with the equivalent for move_line_key
        # we need to think of how we want to do it

        for move in self:
            move_vals = {
                fname: getattr(move, fname)
                for fname in move._fields.keys()
            }

            format_str = move.picking_id.picking_type_id.u_move_key_format

            if format_str:
                move.u_grouping_key = format_str.format(**move_vals)
            else:
                move.u_grouping_key = None

    def _make_mls_comparison_lambda(self, move_line):
        """ This makes the lambda for
            checking the a move_line
            against move_orign_ids
        """
        lot_name = move_line.lot_id.name or move_line.lot_name
        package = move_line.package_id
        #lot and package
        if lot_name and package:
            return lambda ml: (ml.lot_name == lot_name or \
                               ml.lot_id.name == lot_name) and \
                               ml.result_package_id == package
        # serial
        elif lot_name:
            return lambda ml: ml.lot_name == lot_name or \
                              ml.lot_id.name == lot_name
        # package
        elif package:
            return lambda ml: ml.result_package_id == package
        # products
        else:
            # This probaly isn't to be trusted
            return lambda ml: ml.location_dest_id == move_line.location_id and \
                              ml.product_id == move_line.product_id

    def update_orig_ids(self, origin_ids):
        """ Updates move_orig_ids based on a given set of
            origin_ids for moves in self by finding the ones
            relevent to the current moves.
        """
        origin_mls = origin_ids.mapped('move_line_ids')
        for move in self:
            # Retain incomplete moves
            updated_origin_ids = move.mapped('move_orig_ids').filtered(
                                            lambda x: x.state not in ('done', 'cancel')
                                            )
            for move_line in move.move_line_ids:
                previous_mls = origin_mls.filtered(
                                            self._make_mls_comparison_lambda(move_line)
                                            )
                updated_origin_ids |= previous_mls.mapped('move_id')
            move.move_orig_ids = updated_origin_ids

    def split_out_move_lines(self, move_lines):
        """ Split sufficient quantity from self to cover move_lines, and
        attach move_lines to the new move. Return the move that now holds all
        of move_lines.
        If self is completely covered by move_lines, it will be removed from
        its picking and returned.
        Preconditions: self is a single move,
                       all moves_line are attached to self
        :return: The (possibly new) move that covers all of move_lines,
                 not currently attached to any picking.
        """
        self.ensure_one()
        if not all(ml.move_id == self for ml in move_lines):
            raise ValueError(_("Cannot split move lines from a move they are"
                               "not part of."))
        if move_lines == self.move_line_ids and \
                not self.move_orig_ids.filtered(
                    lambda x: x.state not in ('done', 'cancel')):
            bk_move = self
            bk_move.write({'picking_id': None})
        else:
            # TODO: consider using odoo core stock.move._split?
            total_ordered_qty = sum(move_lines.mapped('ordered_qty'))
            total_initial_qty = sum(move_lines.mapped('product_uom_qty'))
            bk_move = self.copy({
                'picking_id': False,
                'move_line_ids': [],
                'move_orig_ids': [],
                # move_dest_ids not copied by default
                # WS-MPS: this might need to be refined like move_orig_ids
                'move_dest_ids': [(6, 0, self.move_dest_ids.ids)],
                'ordered_qty': total_ordered_qty,
                'product_uom_qty': total_initial_qty,
                'state': self.state,
            })
            move_lines.write({
                'move_id': bk_move.id,
                'state': self.state,
                'picking_id': None,
            })
            self.with_context(bypass_reservation_update=True).write({
                'ordered_qty': self.ordered_qty - total_ordered_qty,
                'product_uom_qty': self.product_uom_qty - total_initial_qty,
            })

            if self.move_orig_ids:
                (bk_move | self).update_orig_ids(self.move_orig_ids)

        return bk_move

    def action_refactor(self):
        """Refactor all the moves in self. May result in the moves being changed
        and/or their associated pickings being deleted."""
        self._action_refactor()
        return True

    def _action_refactor(self, stage=None):
        """Refactor moves in self.
        :param stage: One of confirm|assign|done, if set, filters the moves
            which will be refactored to only the state(s) that match:
                - 'confirm': confirmed, waiting
                - 'assign': assigned, partially_available
                - 'done': done

           Methods doing a refactor are expected to take a single recordset of
           moves on which they will act, and to return the recordset of
           equivalent moves after they have been transformed.
           The output moves may be identical to the input, may contain none
           of the input moves, or anywhere in between.
           The output should contain a functionally similar set of moves.
        """
        if stage is not None and stage not in STAGES.values():
            raise UserError(_("Unknown stage for move refactor: %s") % stage)
        moves = self

        rf_moves = moves.filtered(
            lambda m: m.picking_type_id and m.state not in ['draft', 'cancel']
        )
        if stage is not None:
            rf_moves = rf_moves.filtered(lambda m: STAGES[m.state] == stage)

        for picking_type, pt_moves in rf_moves.groupby('picking_type_id'):
            for stage, st_moves in pt_moves.groupby(lambda m: STAGES[m.state]):
                if stage == 'confirm':
                    action = picking_type.u_post_confirm_action
                elif stage == 'assign':
                    action = picking_type.u_post_assign_action
                elif stage == 'validate':
                    action = picking_type.u_post_validate_action
                else:
                    continue  # Don't refactor cancel or draft moves.

                if action:
                    _logger.info("Refactoring %s at %s using %s: %s",
                                 picking_type.name, stage, action, st_moves.ids)
                    func = getattr(st_moves, 'refactor_action_' + action)
                    new_moves = func()
                    if new_moves is not None:
                        moves -= st_moves
                        moves |= new_moves

        return moves

    def _action_confirm(self, *args, **kwargs):
        """Extend _action_confirm to trigger refactor action.

        Odoos move._action_confirm returns all the moves passed in to it, after
        merging any it can. In places the return value is used to immediately
        assign, so any created moves should be returned.

        However, in stock.move._split() in Odoo core, _action_confirm is
        called on a single move and it expects a single move to be returned
        (will error out if not). Therefore the refactor at confirm should avoid
        splitting/creating moves. Luckily this is unlikely to be an issue as
        it makes little sense to split moves at this stage, before they have
        stock reserved against them.
        """
        res = super(StockMove, self)._action_confirm(*args, **kwargs)
        post_refactor_moves = res._action_refactor(stage='confirm')

        if post_refactor_moves != res:
            raise UserError(_("Post confirm refactor has created or destroyed "
                              "moves, which could break things if you have the "
                              "MRP module installed"))
        return res

    def _action_assign(self):
        """Extend _action_assign to trigger refactor action and preprocess
        location suggestions.
        n.b. _action_assign does not return anything in core Odoo, so we
        don't return any extra moves that may have been created
        by refactoring.
        """
        res = super(StockMove, self)._action_assign()

        assign_moves = self.exists()._action_refactor(stage='assign')

        for picking_type, moves in assign_moves.groupby('picking_type_id'):
            # location suggestions
            if picking_type.u_drop_location_preprocess:
                moves.mapped('picking_id').apply_drop_location_policy()
        return res

    def _action_done(self):
        """Extend _action_done to trigger refactor action, and push from drop

        Odoo returns completed moves.
        Therefore we will keep track of moves created by the refactor and
        return them as part of the set of completed moves.
        """
        done_moves = super(StockMove, self)._action_done()

        post_refactor_done_moves = done_moves._action_refactor(stage='validate')

        post_refactor_done_moves.push_from_drop()

        return post_refactor_done_moves

    def push_from_drop(self):
        Move = self.env['stock.move']
        MoveLine = self.env['stock.move.line']
        Push = self.env['stock.location.path']

        done_moves = self.filtered(lambda m: m.state == 'done')

        # load all the move lines, grouped by location
        move_lines_by_location = done_moves.mapped('move_line_ids').groupby('location_dest_id')

        # Build mapping of push rule -> move lines to push
        move_lines_by_push = {}
        for location, loc_mls in move_lines_by_location:
            # Get the push rule that moves from the location.
            push_step = Push.get_path_from_location(location)
            if not push_step:
                continue
            if push_step not in move_lines_by_push:
                move_lines_by_push[push_step] = MoveLine.browse()
            move_lines_by_push[push_step] |= loc_mls

        created_moves = Move.browse()
        for push, move_lines in move_lines_by_push.items():
            created_moves |= self._create_moves_for_push(push, move_lines)

        confirmed_moves = created_moves._action_confirm()
        confirmed_moves._action_assign()

    @api.model
    def _create_moves_for_push(self, push, move_lines):
        """Create moves for a push rule to cover the quantity in move_lines"""
        Move = self.env['stock.move']

        # Group mls by move so we can preserve move information.
        mls_by_move = move_lines.groupby('move_id')
        created_moves = Move.browse()
        base_vals = {
            'picking_type_id': push.picking_type_id.id,
            'location_id': push.location_from_id.id,
            'location_dest_id': push.location_dest_id.id,
            'picking_id': None,
        }
        for move, mls in mls_by_move:
            move_vals = base_vals.copy()
            move_vals.update({
                'product_uom_qty': sum(mls.mapped('qty_done')),
                # FIXME: CWR: This is commented out because odoo does not limit
                # TODO: reservation to the src location of a move if it has
                # TODO: preceeding moves.
                # TODO: Uncomment this, and unskip tests, when story/1934 is completed
                # 'move_orig_ids': [(6, 0, [move.id,])]
            })
            created_moves |= move.copy(move_vals)
        return created_moves

    def group_by_key(self):

        # TODO MTC: This can be refactored and abstracted at some point with
        # this with the equivalent for move_line_key
        # we need to think of how we want to do it

        # force recompute on u_grouping_key so we have an up-to-date key:
        self._fields['u_grouping_key'].compute_value(self)

        if any(pt.u_move_key_format is False
               for pt in self.mapped('picking_id.picking_type_id')):
            raise UserError(_("Cannot group moves when their picking type"
                              "has no grouping key set."))

        return self.groupby(lambda ml: ml.u_grouping_key)

    def refactor_action_group_by_move_key(self):
        """
        group the moves by the splitting criteria
        for each resulting group of stock.moves:
            create a new picking
            attach the stock.moves to the new picking.
        """
        # TODO MTC: This can be refactored and abstracted at some point with
        # this with the equivalent for move_line_key
        # we need to think of how we want to do it

        Picking = self.env['stock.picking']

        picking_type = self.mapped('picking_type_id')
        picking_type.ensure_one()

        if not picking_type.u_move_key_format:
            return

        pickings = self.mapped('picking_id')

        for key, move_group in self.group_by_key():

            if len(move_group.mapped('location_id')) > 1 or \
                    len(move_group.mapped('location_dest_id')) > 1:
                raise UserError(
                    _('Move grouping has generated a group of'
                      'moves that has more than one source or '
                      'destination location. Aborting. key: "%s", '
                      'location_ids: "%s", location_dest_ids: "%s"'
                      '') % (key, move_group.mapped('location_id'),
                             move_group.mapped('location_dest_id')))

            group_pickings = move_group.mapped('picking_id')
            origin = None
            if len(group_pickings) == 1:
                origin = group_pickings.origin

            Picking._new_picking_for_group(key, move_group, origin=origin)

        empty_picks = pickings.filtered(lambda p: len(p.move_lines) == 0)
        if empty_picks:
            _logger.info(_("Cancelling empty picks after splitting."))
            # action_cancel does not cancel a picking with no moves.
            empty_picks.write({
                'state': 'cancel',
                'is_locked': True
            })

        return self

    def refactor_action_group_by_move_line_key(self):
        """
        group the move lines by the splitting criteria
        for each resulting group of stock.move.lines:
            create a new picking
            split any stock.move records that are only partially covered by the
                group of stock.moves
            attach the stock.moves and stock.move.lines to the new picking.
        """
        Move = self.env['stock.move']
        Picking = self.env['stock.picking']

        picking_type = self.mapped('picking_type_id')
        picking_type.ensure_one()

        if not picking_type.u_move_line_key_format:
            return

        pickings = self.mapped('picking_id')
        mls_by_key = self.mapped('move_line_ids').group_by_key()

        result_moves = Move.browse()

        for key, ml_group in mls_by_key.items():
            touched_moves = ml_group.mapped('move_id')

            if len(touched_moves.mapped('location_id')) > 1 or \
                    len(touched_moves.mapped('location_dest_id')) > 1:
                raise UserError(_('Move Line grouping has generated a group of'
                                  'moves that has more than one source or '
                                  'destination location. Aborting. key: "%s", '
                                  'location_ids: "%s", location_dest_ids: "%s"'
                                  '') % (key, touched_moves.mapped('location_id'),
                                         touched_moves.mapped('location_dest_id')))

            group_moves = Move.browse()
            group_pickings = Picking.browse()
            for move in touched_moves:
                group_pickings |= move.picking_id
                move_mls = ml_group.filtered(lambda l: l.move_id == move)

                if move_mls != move.move_line_ids:
                    # The move is not entirely contained by the move lines
                    # for this grouping. Need to split the move.
                    group_moves |= move.split_out_move_lines(move_mls)
                else:
                    group_moves |= move

            origin = None
            if len(group_pickings) == 1:
                origin = group_pickings.origin
            Picking._new_picking_for_group(key, group_moves, origin=origin)
            result_moves |= group_moves

        # NOTE: empty pick = no moves and no move_lines
        empty_picks = pickings.filtered(lambda p: len(p.move_lines) == 0)
        if empty_picks:
            _logger.info(_("Cancelling empty picks after splitting."))
            # action_cancel does not cancel a picking with no moves.
            empty_picks.write({
                'state': 'cancel',
                'is_locked': True
            })

        return result_moves
