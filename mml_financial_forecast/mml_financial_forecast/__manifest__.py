{
    'name': 'MML Financial Forecast',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Forecasting',
    'summary': 'Driver-based financial forecasting from ROQ demand signals',
    'description': """
        Full P&L, cash flow, and scenario planning engine.
        Pulls unit forecasts from ROQ module, computes revenue/COGS/margin
        with configurable FX rates, freight, duty, and customer payment terms.
    """,
    'author': 'MML Consumer Products Ltd',
    'website': 'https://www.mml.co.nz',
    'depends': [
        'base',
        'product',
        'sale',
        'purchase',
        'account',
        'stock',
        'mail',
        # 'mml_roq',  # Uncomment when ROQ module is available
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/default_data.xml',
        'views/forecast_config_views.xml',
        'views/forecast_fx_rate_views.xml',
        'views/forecast_customer_term_views.xml',
        'views/forecast_opex_views.xml',
        'views/forecast_summary_views.xml',
        'views/menu_views.xml',
        'wizard/forecast_generate_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
