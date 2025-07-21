from flask import Flask, render_template
import pandas as pd
import os
import json
import csv
import requests
import time
from datetime import datetime
from threading import Thread

app = Flask(__name__)

# ========== CONFIG ==========
TRACKED_ASSETS = ["USDC", "BTC", "ETH", "SOL", "SUI", "XRP", "BNB", "DOGE", "LTC", "ADA", "AVAX", "TRUMP", "LINK", "WLD", "OP", "ARB", "TON", "BLUR", "MAGIC", "PYTH", "INJ", "TIA", "ZRO", "ZETA", "DYM", "JUP", "MANTA", "ONDO", "LISTA", "ENA", "ZK", "XLM", "TRX", "FIL", "GMX", "TAO", "EDU"]  # Có thể mở rộng thêm coin nếu muốn

# ========== 1. LOG 1H: OI, Long/Short, Volume, Avg Price ==========
def get_long_account_data(asset):
    try:
        url = f"https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol={asset}USDT&period=1h&limit=1"
        res = requests.get(url).json()
        if not res or not isinstance(res, list):
            return None
        long_acc = float(res[0].get("longAccount", 0))
        short_acc = 100.0 - long_acc
        return long_acc, short_acc
    except:
        return None

def get_long_short_ratio(asset):
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={asset}USDT&period=1h&limit=1"
        res = requests.get(url).json()
        if not res or not isinstance(res, list):
            return None
        return float(res[0].get("longShortRatio", 0))
    except:
        return None

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
        ratio = get_long_short_ratio(asset)
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

def log_data_1h():
    while True:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:00:00")
        for asset in TRACKED_ASSETS:
            longshort = get_long_account_data(asset)
            ratio = get_long_short_ratio(asset)
            oi_usd, oi_btc = get_open_interest(asset)
            vol_long, vol_short, avg_long, avg_short = get_volume_price(asset)

            def append(file, fields, headers):
                ensure_file(file, headers)
                with open(file, "a") as f:
                    f.write(f"{now},{asset}," + ",".join(map(str, fields)) + "\n")

            if longshort and ratio is not None:
                append("longshort_history.csv", [longshort[0], longshort[1], ratio], ["long_account", "short_account", "long_short_ratio"])
            if oi_usd is not None and oi_btc is not None:
                append("oi_history.csv", [oi_usd, oi_btc], ["oi_usd", "oi_btc"])
            if vol_long and vol_short:
                append("volume_history.csv", [vol_long, vol_short], ["volume_long", "volume_short"])
            if avg_long and avg_short:
                append("avgprice_history.csv", [avg_long, avg_short], ["avg_price_long", "avg_price_short"])
        time.sleep(1800)

# ========== 2. LOG 1M: Price & Volume ==========
def log_price_volume_1m():
    while True:
        os.makedirs("data", exist_ok=True)
        for asset in TRACKED_ASSETS:
            try:
                res = requests.get(f"https://api.kucoin.com/api/v1/market/stats?symbol={asset}-USDT").json()
                price = float(res["data"]["last"])
                volume = float(res["data"]["volValue"])
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                file_path = f"data/{asset.lower()}_1m.csv"
                with open(file_path, "a", newline='') as f:
                    writer = csv.writer(f)
                    if os.path.getsize(file_path) == 0:
                        writer.writerow(["timestamp", "price", "volume"])
                    writer.writerow([timestamp, price, volume])
            except Exception as e:
                print(f"[ERROR] Logging 1m {asset}: {e}")
        time.sleep(60)

# ========== 3. ROUTE DASHBOARD ==========
@app.route("/")
def index():
    def read_last_row(csv_file, cols):
        if not os.path.exists(csv_file):
            return {}
        try:
            df = pd.read_csv(csv_file, usecols=["timestamp", "asset"] + cols)
        except:
            return {}
        if df.empty:
            return {}
        df = df.sort_values("timestamp").drop_duplicates("asset", keep="last")
        return {
            row["asset"]: {col: row.get(col, None) for col in cols}
            for _, row in df.iterrows()
        }

    longshort = read_last_row("longshort_history.csv", ["long_account", "short_account", "long_short_ratio"])
    oi = read_last_row("oi_history.csv", ["oi_usd", "oi_btc"])
    volume = read_last_row("volume_history.csv", ["volume_long", "volume_short"])
    avgprice = read_last_row("avgprice_history.csv", ["avg_price_long", "avg_price_short"])

    data = []
    for asset in TRACKED_ASSETS:
        row = {
            "asset": asset,
            "long_account": f"{float(longshort.get(asset, {}).get('long_account', 0)):.2f}%" if longshort.get(asset) else "-",
            "short_account": f"{float(longshort.get(asset, {}).get('short_account', 0)):.2f}%" if longshort.get(asset) else "-",
            "long_short_ratio": f"{float(longshort.get(asset, {}).get('long_short_ratio', 0)):.2f}" if longshort.get(asset) else "-",
            "oi_usd": f"{float(oi.get(asset, {}).get('oi_usd', 0)):.2f}" if oi.get(asset) else "-",
            "oi_btc": f"{float(oi.get(asset, {}).get('oi_btc', 0)):.4f}" if oi.get(asset) else "-",
            "volume_long": f"{float(volume.get(asset, {}).get('volume_long', 0)):.2f}" if volume.get(asset) else "-",
            "volume_short": f"{float(volume.get(asset, {}).get('volume_short', 0)):.2f}" if volume.get(asset) else "-",
            "avg_price_long": f"{float(avgprice.get(asset, {}).get('avg_price_long', 0)):.4f}" if avgprice.get(asset) else "-",
            "avg_price_short": f"{float(avgprice.get(asset, {}).get('avg_price_short', 0)):.4f}" if avgprice.get(asset) else "-",
        }
        data.append(row)
    return render_template("index.html", data=data)

# ========== 4. ROUTE BIỂU ĐỒ 1M ==========
@app.route("/chart1m/<asset>")
def chart_1m(asset):
    try:
        file_path = f"data/{asset.lower()}_1m.csv"
        if not os.path.exists(file_path):
            return f"No data for {asset}"

        df = pd.read_csv(file_path)
        if df.empty or len(df) < 3:  # ✅ Kiểm tra có ít nhất 3 dòng mới render
            return f"⏳ Đang thu thập dữ liệu... Hãy thử lại sau 1–2 phút"

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("Asia/Bangkok")
        df = df.tail(60)

        labels = df["timestamp"].dt.strftime("%H:%M:%S").tolist()
        prices = df["price"].tolist()
        volumes = df["volume"].tolist()

        if len(labels) < 3 or len(prices) < 3 or len(volumes) < 3:
            return "⚠️ Dữ liệu chưa đầy đủ. Đợi vài phút rồi F5 lại nhé."

        return render_template(
            "chart_1m.html",
            asset=asset.upper(),
            labels=json.dumps(labels),
            price=json.dumps(prices),
            volume=json.dumps(volumes)
        )
    except Exception as e:
        return f"Error loading chart for {asset}: {e}"
        
# ========== RUN ==========
if __name__ == "__main__":
    Thread(target=log_data_1h, daemon=True).start()
    Thread(target=log_price_volume_1m, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))