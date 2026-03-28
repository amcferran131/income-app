from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import calendar
import re
from collections import Counter

app = Flask(__name__)

ALLOWED_ORIGIN = 'https://dividend-calculator-blond.vercel.app'

@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin', '')
    if origin == ALLOWED_ORIGIN:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/dividends', methods=['OPTIONS'])
def dividends_preflight():
    return add_cors(app.make_default_options_response())

TRANSLATIONS = {
    'ATH-B': 'ATH-PB', 'ATH/PRB': 'ATH-PB',
    'CODI-A': 'CODI-PA', 'CODI/PRA': 'CODI-PA',
    'COF-I': 'COF-PI', 'COF/PRI': 'COF-PI',
    'EQH-A': 'EQH-PA', 'EQH/PRA': 'EQH-PA',
    'WFC/PRL': 'WFC-PL', 'WFC-L': 'WFC-PL',
    'JPM/PRM': 'JPM-PM', 'JPM-M': 'JPM-PM',
    'MET/PRF': 'MET-PF', 'MET-F': 'MET-PF',
    'AXS/PRE': 'AXS-PE',
}

# Tickers whose sec_type cannot be inferred from Yahoo Finance metadata and must be
# hard-coded. DCOMP (Dime Community Bancshares preferred) returns only the plain
# company name with no preferred keywords, percentage, or '- D' shortName suffix.
SEC_TYPE_OVERRIDES = {
    'DCOMP': 'preferred',
    'AFSIA': 'preferred',
    'AFSIC': 'preferred',
    'HBANP': 'preferred',
    'OZKAP': 'preferred',
}


def _cutoff(index, months):
    """Return a cutoff Timestamp compatible with the index's timezone."""
    ts = pd.Timestamp.now(tz='UTC') - pd.DateOffset(months=months)
    return ts.tz_localize(None) if index.tz is None else ts


def _payment_month(dt):
    """Normalize a payment date to its intended month.

    Payments on days 1–4 are almost always a prior-month payment pushed forward
    by a weekend/holiday (e.g. May 1 = intended April 30). Attribute those to
    the previous month so quarterly cycle detection is accurate.
    """
    if dt.day <= 4:
        return dt.month
    return dt.month


def detect_freq_id(div_history, frequency):
    """Determine freqId from actual payment month patterns in dividend history."""
    if frequency == 0:
        return None
    if frequency == 12:
        return 'monthly'

    # Use last 36 months for a reliable sample
    recent = div_history[div_history.index > _cutoff(div_history.index, 36)]
    if recent.empty:
        return None

    months = [_payment_month(d) for d in recent.index]

    if frequency == 4:
        # Jan/Apr/Jul/Oct → m%3==1 → q_jan
        # Feb/May/Aug/Nov → m%3==2 → q_feb
        # Mar/Jun/Sep/Dec → m%3==0 → q_mar
        counts = Counter(m % 3 for m in months)
        dominant = counts.most_common(1)[0][0]
        return {1: 'q_jan', 2: 'q_feb', 0: 'q_mar'}[dominant]

    if frequency == 2:
        # Fold each month into its base (1–6) by subtracting 6 from second half
        base_months = [m if m <= 6 else m - 6 for m in months]
        counts = Counter(base_months)
        base = counts.most_common(1)[0][0]
        labels = {1: 'semi_jan', 2: 'semi_feb', 3: 'semi_mar',
                  4: 'semi_apr', 5: 'semi_may', 6: 'semi_jun'}
        return labels.get(base)

    if frequency == 1:
        counts = Counter(months)
        m = counts.most_common(1)[0][0]
        return f'annual_{calendar.month_abbr[m].lower()}'

    return None


def detect_sec_type(clean_sym, info):
    """Classify security type using symbol pattern and Yahoo Finance metadata.

    Priority order:
      1. Preferred  — symbol contains '-P' (e.g. WFC-PL, JPM-PM)
      2. Preferred  — name contains preferred keywords (PFD, PREFERRED, PFD SER, etc.)
      3. Preferred  — name contains a coupon-rate pattern (e.g. 6.75%, 5.5%)
      4. Preferred  — shortName ends with ' - D' or ' - d' (Yahoo depositary share marker,
                      e.g. BHFAN/BHFAO/BHFAP → 'Brighthouse Financial, Inc. - D')
      5. ETF        — quoteType == 'ETF'
      6. REIT       — sector == 'Real Estate'
      7. Stock      — everything else

    Note: DCOMP (Dime Community Bancshares) returns no preferred indicators from Yahoo
    Finance (plain company name, no ' - D' suffix). It cannot be auto-detected as
    preferred from metadata alone; add it to TRANSLATIONS or set type manually.
    """
    # 1. Symbol pattern: dash followed by P (e.g. WFC-PL, ATH-PB)
    if '-P' in clean_sym.upper():
        return 'preferred'

    long_name = (info.get('longName') or '').upper()
    short_name_raw = (info.get('shortName') or '')
    combined = long_name or short_name_raw.upper()

    # 2. Name keywords
    PREFERRED_KEYWORDS = (
        'PREFERRED', 'PFD', 'PFDPFD', 'PFD SER',
        'DEP SHS', 'DEPOSITARY SHS', 'DEP. SHS',
    )
    if any(kw in combined for kw in PREFERRED_KEYWORDS):
        return 'preferred'

    # 3. Coupon-rate pattern in name: "6.75%", "5.5%", "7.25%", etc.
    if re.search(r'\d+\.?\d*\s*%', combined):
        return 'preferred'

    # 4. Yahoo Finance shortName ' - D' / ' - d' suffix (depositary preferred marker)
    #    Catches BHFAN, BHFAO, BHFAP and similar series where the name body is plain
    if short_name_raw.strip().endswith((' - D', ' - d')):
        return 'preferred'

    # 5. ETF
    quote_type = (info.get('quoteType') or '').upper()
    if quote_type == 'ETF':
        return 'bond'

    # 6. REIT
    sector = (info.get('sector') or '').lower()
    if 'real estate' in sector:
        return 'reit'

    return 'stock'


def lookup_ticker(original_sym):
    clean_sym = TRANSLATIONS.get(original_sym, original_sym.replace('/', '-'))
    ticker = yf.Ticker(clean_sym)

    # Money market: fixed 4% annual yield
    if clean_sym == 'SWVXX':
        hist = ticker.history(period="5d")
        if hist.empty:
            return None, f"{clean_sym}: no price data"
        price = hist['Close'].iloc[-1]
        return {
            'symbol': original_sym,
            'yahoo_symbol': clean_sym,
            'sec_type': 'cd',
            'price': round(float(price), 2),
            'dividend_per_share': round(price * 0.04, 4),
            'payment_frequency': 12,
            'annual_income_per_share': round(price * 0.04, 4),
            'freqId': 'monthly',
            'last_payment_date': None,
            'note': 'Money market — 4% annual yield applied to NAV',
        }, None

    # Fetch metadata once; fall back to empty dict on any error
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    sec_type = SEC_TYPE_OVERRIDES.get(original_sym) or detect_sec_type(clean_sym, info)

    # Standard dividend logic
    div_history = ticker.dividends
    last_12 = div_history[div_history.index > _cutoff(div_history.index, 12)]
    annual_div_per_share = round(float(last_12.sum()), 4)

    last_24 = div_history[div_history.index > _cutoff(div_history.index, 24)]
    payment_count = len(last_24)
    if payment_count == 0:
        frequency = 0
    else:
        raw_freq = payment_count / 2  # annualize over 24-month window
        # Snap to nearest standard frequency
        frequency = min([1, 2, 4, 12], key=lambda f: abs(f - raw_freq))
    div_per_payment = round(annual_div_per_share / frequency, 4) if frequency else 0.0

    hist = ticker.history(period="5d")
    price = round(float(hist['Close'].iloc[-1]), 2) if not hist.empty else None

    last_payment_date = (
        div_history.index[-1].strftime('%Y-%m-%d') if not div_history.empty else None
    )

    return {
        'symbol': original_sym,
        'yahoo_symbol': clean_sym,
        'sec_type': sec_type,
        'price': price,
        'dividend_per_share': annual_div_per_share,
        'payment_frequency': frequency,
        'dividend_per_payment': div_per_payment,
        'annual_income_per_share': annual_div_per_share,
        'freqId': detect_freq_id(div_history, frequency),
        'last_payment_date': last_payment_date,
    }, None


@app.route('/dividends', methods=['GET', 'POST'])
def dividends():
    """
    Accept a list of ticker symbols and return dividend info for each.

    GET  /dividends?tickers=AAPL,O,SWVXX
    POST /dividends  {"tickers": ["AAPL", "O", "SWVXX"]}
    """
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        tickers = body.get('tickers', [])
    else:
        raw = request.args.get('tickers', '')
        tickers = [t.strip() for t in raw.split(',') if t.strip()]

    if not tickers:
        return jsonify({'error': 'Provide tickers as query param or JSON body'}), 400

    results = []
    errors = []

    for sym in tickers:
        sym = sym.strip().upper()
        try:
            data, err = lookup_ticker(sym)
            if err:
                errors.append({'symbol': sym, 'error': err})
            else:
                results.append(data)
        except Exception as e:
            errors.append({'symbol': sym, 'error': str(e)})

    response = {'results': results}
    if errors:
        response['errors'] = errors

    return jsonify(response)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
