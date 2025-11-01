#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime
import re

class NojimaPriceMonitor:
    def __init__(self):
        self.discord_webhook = os.environ.get('DISCORD_WEBHOOK', '')
        urls_str = os.environ.get('MONITOR_URLS', '')
        self.urls = [url.strip() for url in urls_str.split(',') if url.strip()]
        self.check_interval = int(os.environ.get('CHECK_INTERVAL', '300'))
        self.price_data_file = "price_data.json"
        self.previous_prices = self.load_previous_prices()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
        }
    
    def load_previous_prices(self):
        if os.path.exists(self.price_data_file):
            try:
                with open(self.price_data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_prices(self):
        with open(self.price_data_file, 'w', encoding='utf-8') as f:
            json.dump(self.previous_prices, f, ensure_ascii=False, indent=2)
    
    def extract_price(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        price_patterns = [
            {'class_': re.compile(r'.*price.*', re.I)},
            {'class_': re.compile(r'.*value.*', re.I)},
            {'itemprop': 'price'},
        ]
        for pattern in price_patterns:
            elements = soup.find_all(attrs=pattern)
            for element in elements:
                text = element.get_text()
                price_match = re.search(r'[¥￥]?\s*([0-9,]+)\s*円?', text)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    try:
                        price = int(price_str)
                        if 100 <= price <= 10000000:
                            return price
                    except ValueError:
                        continue
        all_text = soup.get_text()
        prices = re.findall(r'[¥￥]?\s*([0-9,]{3,})\s*円', all_text)
        for price_str in prices:
            try:
                price = int(price_str.replace(',', ''))
                if 100 <= price <= 10000000:
                    return price
            except ValueError:
                continue
        return None
    
    def extract_product_name(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        patterns = [soup.find('h1'), soup.find('h2', class_=re.compile(r'.*product.*', re.I)), soup.find('title')]
        for element in patterns:
            if element:
                text = element.get_text().strip()
                text = re.sub(r'[\|｜].*$', '', text)
                text = re.sub(r'\s*-\s*ノジマ.*$', '', text, flags=re.I)
                text = text.strip()
                if text and len(text) > 3:
                    return text
        return "商品名不明"
    
    def check_price(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            current_price = self.extract_price(response.text)
            product_name = self.extract_product_name(response.text)
            if current_price is None:
                print(f"⚠️  価格取得失敗: {product_name}")
                return None
            return {'url': url, 'price': current_price, 'product_name': product_name, 'timestamp': datetime.now().isoformat()}
        except Exception as e:
            print(f"❌ エラー: {str(e)[:100]}")
            return None
    
    def send_discord_notification(self, message, is_price_drop=False):
        if not self.discord_webhook:
            print("⚠️  DISCORD_WEBHOOK未設定")
            return False
        
        # Discord Embed形式で通知
        color = 0x00ff00 if is_price_drop else 0xff9900  # 緑=値下げ、オレンジ=値上げ
        
        embed = {
            "embeds": [{
                "title": "🎉 値下げ検知！" if is_price_drop else "📈 価格変更",
                "description": message,
                "color": color,
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        
        try:
            response = requests.post(self.discord_webhook, json=embed)
            if response.status_code == 204:
                print("✅ Discord通知送信成功")
                return True
            else:
                print(f"⚠️  Discord通知失敗: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Discord通知エラー: {e}")
            return False
    
    def notify(self, message, is_price_drop=False):
        print("\n" + "="*60)
        print(f"🔔 価格変更検知! {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(message)
        print("="*60 + "\n")
        self.send_discord_notification(message, is_price_drop)
    
    def monitor(self):
        if not self.urls:
            print("❌ MONITOR_URLS未設定")
            return
        print(f"🚀 価格監視開始")
        print(f"💬 Discord: {'有効' if self.discord_webhook else '未設定'}")
        print(f"⏰ 間隔: {self.check_interval}秒")
        print(f"📋 監視: {len(self.urls)}個")
        print(f"{'='*60}\n")
        if self.discord_webhook:
            self.send_discord_notification(
                f"🚀 **価格監視開始**\n\n監視商品数: {len(self.urls)}個\nチェック間隔: {self.check_interval}秒",
                False
            )
        cycle = 0
        while True:
            cycle += 1
            print(f"🔍 #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            for url in self.urls:
                current_data = self.check_price(url)
                if current_data is None:
                    continue
                url = current_data['url']
                current_price = current_data['price']
                product_name = current_data['product_name']
                if url in self.previous_prices:
                    previous_price = self.previous_prices[url]['price']
                    if current_price != previous_price:
                        change = current_price - previous_price
                        change_percent = (change / previous_price) * 100
                        is_price_drop = change < 0
                        emoji = "📉 **値下げ!**" if is_price_drop else "📈 **値上げ**"
                        message = f"{emoji}\n\n**商品:** {product_name}\n**前回:** ¥{previous_price:,}\n**現在:** ¥{current_price:,}\n**変動:** ¥{change:,} ({change_percent:+.1f}%)\n\n[🛒 購入ページへ]({url})"
                        self.notify(message, is_price_drop)
                        self.previous_prices[url] = current_data
                        self.save_prices()
                    else:
                        print(f"  ✓ {product_name[:40]}... ¥{current_price:,}")
                else:
                    print(f"  📝 初回: {product_name[:40]}... ¥{current_price:,}")
                    self.previous_prices[url] = current_data
                    self.save_prices()
                time.sleep(3)
            print(f"⏳ {self.check_interval}秒待機...\n")
            time.sleep(self.check_interval)

if __name__ == "__main__":
    print("="*60)
    print("  ノジマオンライン 価格監視 (Discord)")
    print("="*60 + "\n")
    monitor = NojimaPriceMonitor()
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\n⏹️  停止")
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        time.sleep(60)
