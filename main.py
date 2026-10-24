import os
import time
import re
import sqlite3
import cloudscraper
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

app = Flask(__name__)

# TOKEN VA CHAT_ID ENDI SERVERNING MAXFIY QISMIDAN OLINADI
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

MIN_PRICE_USD = 200
MAX_PRICE_USD = 1000
USD_RATE = 12800

EXCLUDE_KEYWORDS = [
    "stiv", "steve", "rieltor", "makler", "komissiya", "usluga", "agentstvo", "xizmat haqi", 
    "preduprejdeniye", "posrednik", "sotiladi", "prodaja", "sotish", "prodam", "продаётся", 
    "продается", "продам", "продажа", "kupit", "vykup", "ipoteka", "krossovki", "kurtka", 
    "platye", "iron", "utug", "dazmol", "telefon", "odejda", "obuv", "sumka", "soat", "avto", "mashina"
]

MUST_HAVE_HOUSING_KEYWORDS = [
    "kvartira", "ijara", "arenda", "xonali", "komnata", "uchastka", 
    "dacha", "studiya", "novostroyka", "uy ijarasi", "bezmakler", "dom", "аренда", "сдается", "сдаётся"
]

DISTRICTS = [
    "Chilonzor", "Yunusobod", "Mirzo Ulug'bek", "Mirobod", "Yashnobod", 
    "Shayxontohur", "Yakkasaroy", "Olmazor", "Uchtepa", "Sergeli", "Yangihayot", "Bektemir"
]

def init_db():
    conn = sqlite3.connect('tashkent_rents.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seen_urls (
            url TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def is_url_seen(url):
    conn = sqlite3.connect('tashkent_rents.db')
    cursor = conn.cursor()
    cursor.execute('SELECT url FROM seen_urls WHERE url = ?', (url,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def mark_url_seen(url):
    try:
        conn = sqlite3.connect('tashkent_rents.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO seen_urls (url) VALUES (?)', (url,))
        cursor.execute('DELETE FROM seen_urls WHERE url NOT IN (SELECT url FROM seen_urls ORDER BY created_at DESC LIMIT 2000)')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

@app.route('/')
def home():
    return "Tashkent Rental Bot Active & Secure"

def send_startup_notification():
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: BOT_TOKEN or CHAT_ID not found in environment variables!")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "🛡️ <b>Bot xavfsiz rejimda qayta ishga tushdi!</b>\n\n- Token Environment variables orqali himoyalandi.\n- Barcha filtrlar va 15 ta manba nazoratda.",
        "parse_mode": "HTML"
    }
    try:
        scraper.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Startup error: {e}")

def parse_usd_price(price_raw):
    if not price_raw:
        return None, False
    digits = re.findall(r'\d+', price_raw.replace(' ', ''))
    if not digits:
        return price_raw, False
    val = int(digits[0])
    price_lower = price_raw.lower()
    usd_val = val
    if "so'm" in price_lower or "som" in price_lower or "сум" in price_lower or "uzs" in price_lower:
        usd_val = val / USD_RATE
    if MIN_PRICE_USD <= usd_val <= MAX_PRICE_USD:
        return price_raw, True
    return price_raw, False

def detect_district_and_rooms(text):
    district_tag = "#Toshkent"
    for d in DISTRICTS:
        if d.lower() in text.lower():
            district_tag = f"#{d.replace(' ', '').replace('\'', '')}"
            break
    rooms_tag = ""
    match = re.search(r'(\d)\s*(?:xona|xonali|комн|комнатная)', text, re.IGNORECASE)
    if match:
        rooms_tag = f"#{match.group(1)}xonali"
    return district_tag, rooms_tag

def format_price_with_converter(price_raw):
    digits = re.findall(r'\d+', price_raw.replace(' ', ''))
    if not digits:
        return price_raw
    val = int(digits[0])
    price_lower = price_raw.lower()
    if "$" in price_raw or "y.e" in price_lower or "sh.b" in price_lower or "usd" in price_lower:
        som_val = val * USD_RATE
        return f"{val:,} $  (~{som_val:,} so'm)"
    elif "so'm" in price_lower or "som" in price_lower or "сум" in price_lower or "uzs" in price_lower:
        usd_val = round(val / USD_RATE)
        return f"{val:,} so'm  (~{usd_val:,} $)"
    return price_raw

def send_telegram_media_group(source_name, title, link, price, description, images):
    if not BOT_TOKEN or not CHAT_ID:
        return
    district_tag, rooms_tag = detect_district_and_rooms(title + " " + description)
    formatted_price = format_price_with_converter(price) or price

    caption = (
        f"🔰 <b>Kvartira Ijarasi | Maklersiz ✅️</b>\n\n"
        f"📌 <b>Sarlavha:</b> {title[:120]}\n"
        f"💵 <b>Narxi:</b> {formatted_price}\n"
        f"📝 <b>Ma'lumotlar:</b>\n{description[:450]}\n\n"
        f"📍 <b>Manba:</b> #{source_name}\n"
        f"🔍 <b>Teglar:</b> {district_tag} {rooms_tag}\n"
        f"🔗 <a href='{link}'>E'lonni ko'rish uchun bosing</a>"
    )

    valid_images = [img for img in images if img and img.startswith('http')][:10]

    if valid_images:
        if len(valid_images) == 1:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": valid_images[0], "caption": caption, "parse_mode": "HTML"}
            try:
                scraper.post(url, json=payload, timeout=12)
            except Exception as e:
                print(f"Telegram photo error: {e}")
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
            media = []
            for idx, img in enumerate(valid_images):
                item = {"type": "photo", "media": img}
                if idx == 0:
                    item["caption"] = caption
                    item["parse_mode"] = "HTML"
                media.append(item)
            payload = {"chat_id": CHAT_ID, "media": media}
            try:
                scraper.post(url, json=payload, timeout=15)
            except Exception as e:
                print(f"Telegram media group error: {e}")
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": False}
        try:
            scraper.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram text error: {e}")

def is_valid_rental(text):
    if not text:
        return False
    text_lower = text.lower()
    if any(kw in text_lower for kw in EXCLUDE_KEYWORDS):
        return False
    if not any(rh in text_lower for rh in MUST_HAVE_HOUSING_KEYWORDS):
        return False
    return True

def is_bad_link(link):
    bad_tokens = ['play.google.com', 'apps.apple.com', 'facebook.com', 'instagram.com', 'telegram.org', 't.me']
    return any(b in link.lower() for b in bad_tokens)

def extract_full_details(link, base_url):
    images = []
    price = None
    description = ""
    try:
        res = scraper.get(link, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            img_tags = soup.find_all('img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    if not src.startswith('http'):
                        src = base_url.rstrip('/') + '/' + src.lstrip('/')
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']) and not any(b in src.lower() for b in ['logo', 'icon', 'avatar', 'banner', 'button']):
                        if src not in images:
                            images.append(src)

            price_elem = soup.find(re.compile(r'(span|div|p|h3)'), class_=re.compile(r'(price|narx)', re.I)) or soup.find(attrs={"data-testid": "ad-price"})
            if price_elem:
                raw_price = price_elem.text.strip()
                if any(c.isdigit() for c in raw_price):
                    price = raw_price
            
            if not price:
                prices = re.findall(r'(\d+[\d\s\.,]*\s*(?:sh\.b|sh\.b\.|y\.e\.|y\.e|\$|so\'m|som|у\.е\.|у\.е|сум|сўм|руб|usd|uzs))', res.text, re.IGNORECASE)
                if prices:
                    price = prices[0].strip()

            desc_elem = soup.find(re.compile(r'(div|p|section)'), class_=re.compile(r'(description|details|matn|text)', re.I)) or soup.find(attrs={"data-testid": "ad_description"})
            if desc_elem:
                description = desc_elem.text.strip()
            else:
                description = soup.get_text()[:400].replace('\n', ' ')

            return price, description.strip(), images
    except Exception as e:
        print(f"Detail extract error ({link}): {e}")
    return None, "", []

ALL_SOURCES = [
    {"name": "OLX_uz", "url": "https://www.olx.uz/oz/nedvizhimost/kvartiry/arenda-dlitelno/tashkent/"},
    {"name": "Uybor", "url": "https://uybor.uz/uz/listings/tashkent/rent-apartments"},
    {"name": "Rentli", "url": "https://rentli.uz/uz/rent"},
    {"name": "Egasi_uz", "url": "https://egasi.uz/uz/arenda"},
    {"name": "Realt24", "url": "https://realt24.uz/uz/arenda/kvartiry/tashkent/"},
    {"name": "Joyme_uz", "url": "https://joyme.uz/arenda"},
    {"name": "Nomakler", "url": "https://nomakler.uz"},
    {"name": "OsonIjara", "url": "https://osonijara.uz"},
    {"name": "Urbo", "url": "https://urbo.uz"},
    {"name": "UyBozorTV", "url": "https://uybozortv.uz"},
    {"name": "JohnyTop", "url": "https://johnytop.uz"},
    {"name": "iDealMobile", "url": "https://ideal.uz"},
    {"name": "BepulElon", "url": "https://bepulelon.uz"},
    {"name": "Listee", "url": "https://listee.uz"},
    {"name": "BirBir", "url": "https://birbir.uz"}
]

def check_all_sources():
    for p in ALL_SOURCES:
        try:
            res = scraper.get(p["url"], timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                links = soup.find_all('a', href=True)
                for a in links:
                    href = a['href']
                    if len(href) > 5 and not is_bad_link(href):
                        if any(x in href for x in ['/detail', '/property', '/item', '/listing', '/arenda/', '/rent/', '/id', '/d/']):
                            full_link = p["url"].rstrip('/') + href if href.startswith('/') else href
                            if not full_link.startswith('http') or is_bad_link(full_link):
                                continue
                            
                            if not is_url_seen(full_link):
                                title = a.text.strip()
                                full_text = title + " " + href

                                if is_valid_rental(full_text):
                                    price, description, images = extract_full_details(full_link, p["url"])
                                    if price and is_valid_rental(description):
                                        parsed_price, is_in_range = parse_usd_price(price)
                                        if is_in_range:
                                            mark_url_seen(full_link)
                                            send_telegram_media_group(p["name"], title, full_link, parsed_price, description, images)
        except Exception as e:
            print(f"{p['name']} error: {e}")

def scraper_loop():
    send_startup_notification()
    while True:
        try:
            check_all_sources()
        except Exception as e:
            print(f"Global loop error: {e}")
        time.sleep(120)

Thread(target=scraper_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
