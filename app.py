from flask import Flask, render_template
import pandas as pd
import os
import json
import csv
import requests
from datetime import datetime
from threading import Thread

app = Flask(__name__)

TRACKED_ASSETS = [
    "USDT", "USDC", "BTC", "ETH", "SOL", "SUI", "XRP", "BNB", "DOGE", "PEPE", "LTC", "ADA", "AVAX",
    "TRUMP", "LINK", "WLD", "OP", "ARB", "TON", "BLUR", "MAGIC", "MATIC", "PYTH", "INJ", "TIA",
    "ZRO", "ZETA", "DYM", "JUP", "MANTA", "ONDO", "LISTA", "ENA", "ZK", "XLM", "BONK", "WBTC",
    "TRX", "FIL", "GMX", "TAO", "EDU"
]

def get_long_account_data(asset):
    symbol = asset + "USDT"
    try:
        res = requests.get(
            f"https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol={symbol}&period=1h&limit=5"
        ).json()
        if not res or not isinstance(res, list):
            return None
        long_acc = float(res[0].get("longAccount", 0))
        short_acc = 100.0 - long_acc
        return long_acc, short_acc
    except Exception as e:
        print(f"[ERROR] Failed to fetch L/S account for {asset}: {e}")
        return None

def get_long_short_ratio_data(asset):
    symbol = asset + "USDT"
    try:
        res = requests.get(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=1"
        ).json()
        if not res or not isinstance(res, list):
            return None
        return float(res[0].get("longShortRatio", 0))
    except Exception as e:
        print(f"[ERROR] get_long_short_ratio_data({asset}): {e}")
        return None

def get_long_short_data(asset):
    acc_data = get_long_account_data(asset)
    if acc_data is None:
        return None, None, None
    long_acc, short_acc = acc_data
    ratio = get_long_short_ratio_data(asset)
    return long_acc, short_acc, ratio

def get_open_interest(asset):
    try:
        oi = requests.get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={asset}USDT").json()
        price = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT").json()
        oi_contracts = float(oi["openInterest"])
        price_usdt = float(price["price"])
        oi_usd = oi_contracts * price_usdt
        return oi_usd, oi_contracts
    except:
        return None, None

def get_volume_price(asset):
    oi_usd, _ = get_open_interest(asset)
    try:
        ratio = get_long_short_ratio_data(asset)
        if ratio is None or oi_usd is None:
            return None, None, None, None
        long_ratio = ratio / (1 + ratio)
        short_ratio = 1 - long_ratio
        price = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT").json()
        p = float(price["price"])
        vol_long = round(oi_usd * long_ratio, 6)
        vol_short = round(oi_usd * short_ratio, 6)
        avg_long = round(p * 1.01, 6)
        avg_short = round(p * 0.99, 6)
        return vol_long, vol_short, avg_long, avg_short
    except:
        return None, None, None, None

def ensure_file(file_path, headers):
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write("timestamp,asset," + ",".join(headers) + "\n")

def log_data():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:00:00")
    for asset in TRACKED_ASSETS:
        long_acc, short_acc, longshort = get_long_short_data(asset)
        oi_usd, oi_btc = get_open_interest(asset)
        vol_long, vol_short, avg_long, avg_short = get_volume_price(asset)

        def append(file, fields, headers):
            ensure_file(file, headers)
            with open(file, "a") as f:
                f.write(f"{now},{asset}," + ",".join(map(str, fields)) + "\n")

        if long_acc is not None and short_acc is not None and longshort is not None:
            append("longshort_history.csv", [long_acc, short_acc, longshort], ["long_account", "short_account", "long_short_ratio"])
        if oi_usd is not None and oi_btc is not None:
            append("oi_history.csv", [oi_usd, oi_btc], ["oi_usd", "oi_btc"])
        if vol_long is not None and vol_short is not None:
            append("volume_history.csv", [vol_long, vol_short], ["volume_long", "volume_short"])
        if avg_long is not None and avg_short is not None:
            append("avgprice_history.csv", [avg_long, avg_short], ["avg_price_long", "avg_price_short"])

def run_scheduler():
    import time
    while True:
        try:
            log_data()
        except Exception as e:
            print("Logging error:", e)
        time.sleep(1800)

def read_last_row(csv_file, cols):
    if not os.path.exists(csv_file):
        return {}
    try:
        df = pd.read_csv(csv_file, usecols=["timestamp", "asset"] + cols)
    except Exception as e:
        print(f"Error reading {csv_file}: {e}")
        return {}
    if df.empty:
        return {}
    df = df.sort_values("timestamp").drop_duplicates("asset", keep="last")
    return {
        row["asset"]: {col: row.get(col, None) for col in cols}
        for _, row in df.iterrows()
    }

@app.route("/")
def index():
    longshort = read_last_row("longshort_history.csv", ["long_account", "short_account", "long_short_ratio"])
    oi = read_last_row("oi_history.csv", ["oi_usd", "oi_btc"])
    volume = read_last_row("volume_history.csv", ["volume_long", "volume_short"])
    avgprice = read_last_row("avgprice_history.csv", ["avg_price_long", "avg_price_short"])

    data = []
    for asset in TRACKED_ASSETS:
        long_acc = longshort.get(asset, {}).get("long_account")
        short_acc = longshort.get(asset, {}).get("short_account")
        longshort_ratio = longshort.get(asset, {}).get("long_short_ratio")

        row = {
            "asset": asset,
            "long_account": f"{float(long_acc):.2f}%" if long_acc is not None else "-",
            "short_account": f"{float(short_acc):.2f}%" if short_acc is not None else "-",
            "long_short_ratio": f"{float(longshort_ratio):.2f}" if longshort_ratio is not None else "-",
            "oi_usd": f"{float(oi.get(asset, {}).get('oi_usd')):,.2f}" if oi.get(asset, {}).get("oi_usd") not in ["-", None] else "-",
            "oi_btc": f"{float(oi.get(asset, {}).get('oi_btc')):,.4f}" if oi.get(asset, {}).get("oi_btc") not in ["-", None] else "-",
            "volume_long": f"{float(volume.get(asset, {}).get('volume_long')):,.2f}" if volume.get(asset, {}).get("volume_long") not in ["-", None] else "-",
            "volume_short": f"{float(volume.get(asset, {}).get('volume_short')):,.2f}" if volume.get(asset, {}).get("volume_short") not in ["-", None] else "-",
            "avg_price_long": f"{float(avgprice.get(asset, {}).get('avg_price_long')):,.4f}" if avgprice.get(asset, {}).get("avg_price_long") not in ["-", None] else "-",
            "avg_price_short": f"{float(avgprice.get(asset, {}).get('avg_price_short')):,.4f}" if avgprice.get(asset, {}).get("avg_price_short") not in ["-", None] else "-",
        }
        data.append(row)
    return render_template("index.html", data=data)

@app.route("/chart1m/<asset>")
def chart_1m(asset):
    try:
        file_path = f"data/{asset.lower()}_1m.csv"
        if not os.path.exists(file_path):
            return f"No data for {asset}"

        df = pd.read_csv(file_path)
        if df.empty or "timestamp" not in df or "price" not in df or "volume" not in df:
            return f"No valid data for {asset}"

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Bangkok")
        df = df.tail(60)  # chỉ lấy 60 phút gần nhất (1h)

        labels = df["timestamp"].dt.strftime("%H:%M:%S").tolist()
        prices = df["price"].tolist()
        volumes = df["volume"].tolist()

        return render_template(
    "chart_1m.html",
    asset=asset.upper(),
    labels=json.dumps(labels),
    price=json.dumps(prices),
    volume=json.dumps(volumes)
)
    except Exception as e:
        return f"Error loading chart for {asset}: {e}"
        
if __name__ == "__main__":
    Thread(target=run_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))