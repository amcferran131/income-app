const API_BASE = 'https://dividend-api-production.up.railway.app';

/**
 * Fetch dividend data for one or more ticker symbols.
 * @param {string[]} tickers - Array of ticker symbols, e.g. ['AAPL', 'O', 'WFC-PL']
 * @returns {Promise<{ results: object[], errors?: object[] }>}
 */
export async function fetchDividends(tickers) {
  if (!Array.isArray(tickers) || tickers.length === 0) {
    throw new Error('tickers must be a non-empty array');
  }

  const response = await fetch(`${API_BASE}/dividends`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${response.status}`);
  }

  return response.json();
}
