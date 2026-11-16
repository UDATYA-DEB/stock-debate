"""Policy thresholds in one place.

These are STARTING VALUES taken from common analyst checklists (which disagree
with each other). Calibrate them once we see real debates; don't treat them as truth.
"""

# History window (DECISIONS 3.5, 3.6)
MAX_YEARS = 5
MIN_YEARS = 3

# Eligibility (Layer 0)
FINANCIAL_SECTORS = {"Financial Services"}  # banks, NBFCs, insurers: excluded in v1 (3.2)
MIN_MARKET_CAP_CRORE = 5_000
MIN_AVG_DAILY_TRADED_VALUE_CRORE = 10

# Red flags (Layer 1)
PLEDGE_MAX_PCT_OF_PROMOTER = 5.0
NEGATIVE_OCF_YEARS_OF_LAST_3 = 2  # triggered if OCF negative in at least this many of the last 3 years
MAX_DEBT_TO_EQUITY = 1.0
MIN_INTEREST_COVERAGE = 3.0  # only matters when debt-to-equity is above the max
MAX_DILUTION_PCT = 10.0  # share count growth over the window
MAX_WORKING_CAPITAL_DAYS_INCREASE_PCT = 30.0  # receivable or inventory days, first vs last year

# Valuation (Layer 3)
RESULTS_LAG_DAYS = 60  # annual results are public roughly this long after the year ends
MIN_PE_HISTORY_DAYS = 250  # about one year of trading days
DCF_DISCOUNT_RATE = 0.12  # rough cost of equity for large Indian companies
DCF_TERMINAL_GROWTH = 0.05
DCF_YEARS = 10
FCF_AVERAGE_YEARS = 3  # smooth the cash-flow base over this many years (partial cycle adjustment)

CRORE = 1e7
