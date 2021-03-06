# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'UDES Stock Functionality',
    'version': '11.0',
    'summary': 'Inventory, Logistics, Warehousing',
    'description': "Holds core functionality for UDES Modules",
    'depends': [
        'sale_stock',
        'stock',
        'stock_picking_batch',
        'blocked_locations',
        'package_hierarchy',
        'print',
        'udes_security',
        'edi',
        'edi_stock',
    ],
    'category': 'Warehouse',
    'sequence': 11,
    'demo': [
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/edi_quant_report_data.xml',
        'data/stock_config.xml',
        'data/locations.xml',
        'data/picking_types.xml',
        'data/product_categories.xml',
        'data/product_packaging.xml',
        'data/picking_print.xml',
        'report/product_product_templates.xml',
        'report/report_stockpicking_operations.xml',
        'views/edi_menu_views.xml',
        'views/edi_quant_report_views.xml',
        'views/product_template.xml',
        'views/res_groups_views.xml',
        'views/res_users_views.xml',
        'views/stock_inventory.xml',
        'views/stock_location.xml',
        'views/stock_move_line_views.xml',
        'views/stock_picking.xml',
        'views/stock_picking_batch.xml',
        'views/stock_picking_type.xml',
        'views/stock_picking_print_strategy_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_warehouse.xml',
        'views/create_planned_transfer_asset.xml',
        'views/web.xml',
        'report/deliveryslip_reports.xml',
        'report/deliveryslip_templates.xml',
        'report/external_layout_standard.xml',
        'report/external_layout.xml',
        'wizard/change_quant_location_view.xml',
        'wizard/refactor_views.xml',
        'security/ir.model.access.csv',
        'security/ir_module_category.xml',
        'security/udes_stock_security.xml',
    ],
    'qweb': [
        'static/src/xml/create_planned_transfer_button.xml'
    ],
    'test': [
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
