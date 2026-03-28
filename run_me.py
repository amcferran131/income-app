import pandas as pd
import yfinance as yf
import os
import time

def run_bot():
    folder = r"C:\Income Bot"
    pos_file = next((f for f in os.listdir(folder) if "position" in f.lower()), None)
    
    if not pos_file:
        print("ERROR: Could not find positions.csv")
        return

    translations = {
        'ATH-B': 'ATH-PB', 'ATH/PRB': 'ATH-PB',
        'CODI-A': 'CODI-PA', 'CODI/PRA': 'CODI-PA',
        'COF-I': 'COF-PI', 'COF/PRI': 'COF-PI',
        'EQH-A': 'EQH-PA', 'EQH/PRA': 'EQH-PA',
        'WFC/PRL': 'WFC-PL', 'WFC-L': 'WFC-PL',
        'JPM/PRM': 'JPM-PM', 'JPM-M': 'JPM-PM',
        'MET/PRF': 'MET-PF', 'MET-F': 'MET-PF',
        'MPW': 'MPW', 'SWVXX': 'SWVXX'
    }

    try:
        raw_data = pd.read_csv(os.path.join(folder, pos_file), encoding='latin1', header=None)
        symbol_row_index = raw_data[raw_data.apply(lambda r: r.astype(str).str.contains('Symbol', case=False).any(), axis=1)].index[0]
        df_live = pd.read_csv(os.path.join(folder, pos_file), skiprows=symbol_row_index, encoding='latin1')
        df_live.columns = [c.strip() for c in df_live.columns]
        col_name = next((c for c in df_live.columns if 'Symbol' in c), None)
        
        print(f"Running Bot with Money Market (4%) Automation...")
        results = []
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        for _, row in df_live.iterrows():
            original_sym = str(row[col_name]).strip().upper()
            
            # Skip options
            if len(original_sym) > 10 and (' ' in original_sym or '/' in original_sym):
                continue
            if 'TOTAL' in original_sym or not original_sym or original_sym == 'NAN': continue
            
            clean_sym = translations.get(original_sym, original_sym.replace('/', '-'))
            print(f" - {original_sym} -> {clean_sym}...", end=" ")
            
            try:
                ticker = yf.Ticker(clean_sym)
                hist = ticker.history(period="5d")
                if hist.empty:
                    print("FAILED")
                    continue
                
                price = hist['Close'].iloc[-1]
                qty_col = next((c for c in df_live.columns if 'Qty' in c), None)
                qty_val = str(row[qty_col]).replace(',', '') if qty_col else "0"
                shares = pd.to_numeric(qty_val, errors='coerce') or 0
                
                # --- SPECIAL MONEY MARKET CALCULATION ---
                if clean_sym == 'SWVXX':
                    annual_div_yield = 0.04  # Set your 4% here
                    annual_income = (price * shares) * annual_div_yield
                    monthly_income = annual_income / 12
                    monthly_map = {m: monthly_income for m in months}
                    print(f"SUCCESS (MM 4% Calc)")
                else:
                    # Standard Dividend Logic
                    div_history = ticker.dividends
                    last_12 = div_history[div_history.index > (pd.Timestamp.now(tz='UTC') - pd.DateOffset(months=12))]
                    annual_div_per_share = last_12.sum()
                    annual_income = annual_div_per_share * shares
                    
                    last_24 = div_history[div_history.index > (pd.Timestamp.now(tz='UTC') - pd.DateOffset(months=24))]
                    pay_months = sorted(last_24.index.month.unique().tolist())
                    div_per_pay = annual_income / len(pay_months) if pay_months else 0
                    monthly_map = {m_name: (div_per_pay if i+1 in pay_months else 0) for i, m_name in enumerate(months)}
                    print(f"SUCCESS")

                results.append({
                    'Symbol': original_sym,
                    'Yahoo Sym': clean_sym,
                    'Shares': shares,
                    'Price': price,
                    'Market Value': price * shares,
                    **monthly_map,
                    'Annual Income': annual_income
                })
                time.sleep(0.5)
            except Exception:
                print("ERROR")
                continue

        df_final = pd.DataFrame(results)
        if not df_final.empty:
            sums = df_final.select_dtypes(include=['number']).sum()
            total_row = pd.DataFrame(columns=df_final.columns)
            total_row.loc[0, 'Symbol'] = 'GRAND TOTAL'
            for col in sums.index:
                total_row.loc[0, col] = sums[col]
            df_final = pd.concat([df_final, total_row], ignore_index=True)

        df_final.to_excel(os.path.join(folder, "Final_Income_Dashboard_2026.xlsx"), index=False)
        print(f"\nFINISH! SWVXX interest calculated.")

    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")

if __name__ == "__main__":
    run_bot()