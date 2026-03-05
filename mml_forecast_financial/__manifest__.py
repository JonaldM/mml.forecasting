{
    'name': 'MML Forecast Financial',
    'version': '19.0.1.0.0',
    'summary': 'P&L and cashflow financial forecasting driven by demand signals',
    'description': 'Financial forecasting module: revenue, COGS, P&L, and cashflow projection driven by demand from mml_forecast_demand.',
    'author': 'MML Consumer Products',
    'category': 'Accounting/Accounting',
    'depends': ['mml_base', 'mml_forecast_core', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/forecast_financial_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
