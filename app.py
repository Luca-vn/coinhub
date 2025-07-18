from flask import Flask, render_template
import pandas as pd
import os
import requests
from datetime import datetime
from threading import Thread

app = Flask(__name__)
TRACKED_ASSETS = ["USDT", "USDC", "BTC", "ETH", "SOL", "SUI", "XRP", "BNB", "DOGE", "PEPE", "LTC", "ADA", "AVAX",
    "TRUMP", "LINK", "WLD", "OP", "ARB", "TON", "BLUR", "MAGIC", "MATIC", "PYTH", "INJ", "TIA",
    "ZRO", "ZETA", "DYM", "JUP", "MANTA", "ONDO", "LISTA", "ENA", "ZK", "XLM", "BONK", "WBTC",
    "TRX", "FIL", "GMX", "TAO", "EDU"]

# == API Functions ==
def get_long_account_data(asset):
    symbol = asset + "USDT"
    try:
        res = requests.get(f"https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol={symbol}&period=1h&limit=2").json()
        if not res or not isinstance(res, list):
            return None
        long_acc = float(res[0].get("longAccount", 0))
        return long_acc
    except Exception as e:
        print(f"[ERROR] get_long_account_data({asset}): {e}")
        return None

def get_long_short_ratio_data(asset):
    symbol = asset + "USDT"
    try:
        res = requests.get(f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=2").json()
        if not res or not isinstance(res, list):
            return None
        ratio = float(res[0].get("longShortRatio", 0))
        return ratio
    except Exception as e:
        print(f"[ERROR] get_long_short_ratio_data({asset}): {e}")
        return None

def get_long_short_data(asset):
    long_acc = get_long_account_data(asset)
    long_short_ratio = get_long_short_ratio_data(asset)
    short_acc = 100.0 - long_acc if long_acc is not None else None
    return long_acc, short_acc, long_short_ratio

def get_open_interest(asset):
    try:
        oi = requests.get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={asset}USDT").json()
        price = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT").json()
        oi_usd = float(oi["openInterest"])
        price_usdt = float(price["price"])
        return oi_usd, oi_usd / price_usdt
    except:
        return None, None

def get_volume_price(asset):
    oi_usd, _ = get_open_interest(asset)
    try:
        price = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT").json()
        p = float(price["price"])
        vol_long = round(float(oi_usd) * 0.6, 6)
        vol_short = round(float(oi_usd) * 0.4, 6)
        avg_long = round(p * 1.01, 6)
        avg_short = round(p * 0.99, 6)
        return vol_long, vol_short, avg_long, avg_short
    except:
        return None, None, None, None

# == Logging ==
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

        if long_acc is not None:
            append("longshort_history.csv", [long_acc, short_acc, longshort], ["long_account", "short_account", "long_short_ratio"])
        if oi_usd is not None:
            append("oi_history.csv", [oi_usd, oi_btc], ["oi_usd", "oi_btc"])
        if vol_long is not None:
            append("volume_history.csv", [vol_long, vol_short], ["volume_long", "volume_short"])
        if avg_long is not None:
            append("avgprice_history.csv", [avg_long, avg_short], ["avg_price_long", "avg_price_short"])

def run_scheduler():
    import time
    while True:
        try:
            log_data()
        except Exception as e:
            print("Logging error:", e)
        time.sleep(3600)

# == Dashboard ==
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
            "oi_usd": oi.get(asset, {}).get("oi_usd", "-"),
            "oi_btc": oi.get(asset, {}).get("oi_btc", "-"),
            "volume_long": volume.get(asset, {}).get("volume_long", "-"),
            "volume_short": volume.get(asset, {}).get("volume_short", "-"),
            "avg_price_long": avgprice.get(asset, {}).get("avg_price_long", "-"),
            "avg_price_short": avgprice.get(asset, {}).get("avg_price_short", "-"),
        }
        data.append(row)
    return render_template("index.html", data=data)

@app.route("/chart/<type>/<asset>")
def chart(type, asset):
    file_map = {
        "long_account": ("longshort_history.csv", "long_account"),
        "short_account": ("longshort_history.csv", "short_account"),
        "long_short_ratio": ("longshort_history.csv", "long_short_ratio"),
        "oi_usd": ("oi_history.csv", "oi_usd"),
        "oi_btc": ("oi_history.csv", "oi_btc"),
        "volume_long": ("volume_history.csv", "volume_long"),
        "volume_short": ("volume_history.csv", "volume_short"),
        "avg_price_long": ("avgprice_history.csv", "avg_price_long"),
        "avg_price_short": ("avgprice_history.csv", "avg_price_short"),
    }
    if type not in file_map:
        return f"Unknown chart type: {type}"
    file, column = file_map[type]
    df = pd.read_csv(file, header=0)
    df = df[df["asset"] == asset]
    if df.empty:
        return f"No data for {asset}"
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC").dt.tz_convert("Asia/Bangkok")
    labels = df["timestamp"].dt.strftime("%m-%d %H:%M").tolist()
    values = df[column].tolist()
    return render_template("chart.html", asset=asset, labels=labels, values=values)

@app.route("/force_log")
def force_log():
    log_data()
    return "Logged!"
    
@app.route("/test_lsr/<asset>")
def test_lsr(asset):
    long_acc = get_long_account_data(asset)
    ratio = get_long_short_ratio_data(asset)
    return f"{asset} → Long%: {long_acc}, Ratio: {ratio}"

if __name__ == "__main__":
    Thread(target=run_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
