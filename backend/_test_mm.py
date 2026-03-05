import asyncio, yfinance as yf
from app.data.yfinance_client import _run_sync

async def test_mm():
    symbols = ['^GSPC', 'DX-Y.NYB']
    df = await _run_sync(lambda: yf.download(symbols, period='1y', interval='1d', progress=False))
    print(f'Shape: {df.shape}')
    close_cols = df['Close'].columns.tolist()
    print(f'Close columns: {close_cols}')
    for sym in symbols:
        try:
            closes = df['Close'][sym].dropna()
            print(f'{sym}: {len(closes)} days, last 3: {closes.values[-3:]}')
            if len(closes) >= 50:
                print(f'  MM50: {closes.values[-50:].mean():.2f}')
            if len(closes) >= 200:
                print(f'  MM200: {closes.values[-200:].mean():.2f}')
        except Exception as e:
            print(f'{sym}: ERROR: {e}')

asyncio.run(test_mm())
