import os
import time
import requests
from bs4 import BeautifulSoup
import cloudscraper

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Faqat eng asosiy makler so'zlarini qoldiramiz
STOP_WORDS = ["rieltor", "makler", "komissiya", "услуга", "агентство"]

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN yoki CHAT_ID sozlanmagan!")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram xatosi: {e}")

def run_scraper():
    print("Scraper ishlamoqda...")
    send_telegram("🚀 Bot qayta sozlandi va e'lonlarni tekshirishni boshladi!")
    
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    sent_ids = set()
    
    while True:
        try:
            url = "https://www.olx.uz/d/oz/nedvizhimost/kvartiry/arenda-dolgosrochnaya/tashkent/"
            res = scraper.get(url, timeout=15)
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                items = soup.find_all('div', {'data-cy': 'l-card'})
                
                for item in items:
                    try:
                        title_elem = item.find('h6')
                        link_elem = item.find('a', href=True)
                        price_elem = item.find('p', {'data-testid': 'ad-price'})
                        
                        if not title_elem or not link_elem:
                            continue
                            
                        title = title_elem.text.strip()
                        link = "https://www.olx.uz" + link_elem['href'] if link_elem['href'].startswith('/') else link_elem['href']
                        price = price_elem.text.strip() if price_elem else "Ko'rsatilmagan"
                        
                        # ID orqali takrorlanmaslik
                        item_id = link.split('/')[-1]
                        if item_id in sent_ids:
                            continue
                            
                        # Stop words tekshiruvi
                        is_broker = any(word in title.lower() for word in STOP_WORDS)
                        if is_broker:
                            continue
                            
                        msg = f"🏠 <b>Yangi e'lon:</b> {title}\n💰 <b>Narx:</b> {price}\n🔗 <a href='{link}'>E'lonni ko'rish</a>"
                        send_telegram(msg)
                        sent_ids.add(item_id)
                        
                    except Exception as ex:
                        continue
            else:
                print(f"Saytdan xatolik qaytdi: {res.status_code}")
                
        except Exception as e:
            print(f"Xatolik: {e}")
            
        time.sleep(180) # 3 daqiqada bir tekshiradi

if __name__ == "__main__":
    run_scraper()
