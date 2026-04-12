from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import calendar
import re
import os
from collections import Counter

app = Flask(__name__)

ALLOWED_ORIGINS = ['https://dividend-calculator-blond.vercel.app', 'https://dividend-finder-two.vercel.app']

@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin', '')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/dividends', methods=['OPTIONS'])
def dividends_preflight():
    return add_cors(app.make_default_options_response())

TRANSLATIONS = {
    'DCIN/PR': 'DCOMP',
    'DCOM/PR': 'DCOMP',
    'DCOM-PR': 'DCOMP',
    'ATH-B': 'ATH-PB', 'ATH/PRB': 'ATH-PB',
    'CODI-A': 'CODI-PA', 'CODI/PRA': 'CODI-PA',
    'COF-I': 'COF-PI', 'COF/PRI': 'COF-PI',
    'EQH-A': 'EQH-PA', 'EQH/PRA': 'EQH-PA',
    'WFC/PRL': 'WFC-PL', 'WFC-L': 'WFC-PL',
    'JPM/PRM': 'JPM-PM', 'JPM-M': 'JPM-PM',
    'MET/PRF': 'MET-PF', 'MET-F': 'MET-PF',
    'AXS/PRE': 'AXS-PE',
}

SEC_TYPE_OVERRIDES = {
    'DCOMP': 'preferred',
    'DCIN/PR': 'preferred',
    'AFSIA': 'preferred',
    'AFSIC': 'preferred',
    'HBANP': 'preferred',
    'OZKAP': 'preferred',
}

def _cutoff(index, months):
    ts = pd.Timestamp.now(tz='UTC') - pd.DateOffset(months=months)
    return ts.tz_localize(None) if index.tz is None else ts

def _payment_month(dt):
    if dt.day <= 4:
        return dt.month
    return dt.month

def detect_freq_id(div_history, frequency):
    if frequency == 0:
        return None
    if frequency == 12:
        return 'monthly'
    recent = div_history[div_history.index > _cutoff(div_history.index, 36)]
    if recent.empty:
        return None
    months = [_payment_month(d) for d in recent.index]
    if frequency == 4:
        counts = Counter(m % 3 for m in months)
        dominant = counts.most_common(1)[0][0]
        return {1: 'q_jan', 2: 'q_feb', 0: 'q_mar'}[dominant]
    if frequency == 2:
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

_PREFERRED_SUFFIXES = frozenset('-P' + c for c in 'ABCDEFGHIJKLMNOPQ')

_PREFERRED_NAME_KEYWORDS = (
    'PREFERRED', 'PFD', 'PFDPFD', 'PFD SER',
    'DEP SHS', 'DEPOSITARY SHS', 'DEP. SHS',
)

def detect_sec_type(original_sym, clean_sym, info):
    override = SEC_TYPE_OVERRIDES.get(original_sym)
    if override:
        return override
    quote_type = (info.get('quoteType') or '').upper()
    sym_upper = clean_sym.upper()
    if quote_type == 'MUTUALFUND' or any(sym_upper.endswith(s) for s in _PREFERRED_SUFFIXES):
        return 'preferred'
    long_name = (info.get('longName') or '').upper()
    short_name_raw = (info.get('shortName') or '')
    combined = long_name or short_name_raw.upper()
    if any(kw in combined for kw in _PREFERRED_NAME_KEYWORDS):
        return 'preferred'
    if re.search(r'\d+\.?\d*\s*%', combined):
        return 'preferred'
    if short_name_raw.strip().endswith((' - D', ' - d')):
        return 'preferred'
    if quote_type == 'ETF':
        return 'bond'
    if 'real estate' in (info.get('sector') or '').lower():
        return 'reit'
    return 'stock'

def lookup_ticker(original_sym):
    clean_sym = TRANSLATIONS.get(original_sym, original_sym.replace('/', '-'))
    ticker = yf.Ticker(clean_sym)
    if original_sym not in TRANSLATIONS and original_sym.endswith('/PR'):
        base_sym = original_sym[:-3]
        test = yf.Ticker(base_sym)
        if not test.dividends.empty:
            clean_sym = base_sym
            ticker = test
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
    try:
        info = ticker.info or {}
    except Exception:
        info = {}
    sec_type = detect_sec_type(original_sym, clean_sym, info)
    div_history = ticker.dividends
    last_12 = div_history[div_history.index > _cutoff(div_history.index, 12)]
    annual_div_per_share = round(float(last_12.sum()), 4)
    last_24 = div_history[div_history.index > _cutoff(div_history.index, 24)]
    payment_count = len(last_24)
    if payment_count == 0:
        frequency = 0
    else:
        raw_freq = payment_count / 2
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
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
