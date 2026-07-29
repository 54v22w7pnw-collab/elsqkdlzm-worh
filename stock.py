import os
import json
import time
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_SITE_URL = "https://mbscorp.co.kr/"
NTFY_TOPIC = "elsqkdlzm-worh26"
STATE_FILE = "state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

KST = timezone(timedelta(hours=9))
TODAY_STR = datetime.now(KST).strftime("%Y-%m-%d")

def send_ntfy(title, message):
    try:
        payload = {
            "topic": NTFY_TOPIC,
            "title": title,
            "message": message,
            "priority": 4
        }
        requests.post("https://ntfy.sh/", json=payload, timeout=5)
        print(f"📱 [알림 발송] {title}")
    except Exception as e:
        print(f"❌ 알림 전송 실패: {e}")

def load_previous_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return None
                if "products" not in data:
                    return {"last_price_alert_date": "", "products": data}
                return data
        except Exception as e:
            print(f"⚠️ 이전 상태 파일 읽기 실패: {e}")
    return None

def save_current_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print("💾 현재 상태 저장 완료 (state.json)")
    except Exception as e:
        print(f"❌ 상태 저장 실패: {e}")

def extract_price(soup):
    try:
        meta_price = soup.find("meta", property="product:price:amount") or soup.find("meta", property="og:price:amount")
        if meta_price and meta_price.get("content"):
            val = int(float(meta_price["content"]))
            return f"{val:,}원"
    except Exception:
        pass

    try:
        price_tag = soup.find("span", id="span_product_price_text") or soup.find("strong", id="span_product_price_text")
        if price_tag and price_tag.text.strip():
            return price_tag.text.strip()
    except Exception:
        pass

    return "가격 정보 없음"

def get_all_category_urls():
    """사이트 메인 및 메뉴에서 모든 카테고리 URL을 자동으로 수집합니다."""
    category_urls = set()
    try:
        res = requests.get(BASE_SITE_URL, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "prod_list.html" in href:
                    full_url = urljoin(BASE_SITE_URL, href)
                    category_urls.add(full_url)
        print(f"📂 자동으로 발견된 카테고리 수: {len(category_urls)}개")
    except Exception as e:
        print(f"⚠️ 카테고리 자동 수집 실패: {e}")
    
    return list(category_urls)

def get_product_links():
    """모든 카테고리를 돌며 개별 상품 링크를 수집합니다."""
    category_urls = get_all_category_urls()
    product_links = set()

    for cat_url in category_urls:
        try:
            res = requests.get(cat_url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.content, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "prod_detail.html" in href:
                    full_url = urljoin(cat_url, href)
                    product_links.add(full_url)
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️ 카테고리 읽기 오류 ({cat_url}): {e}")

    return list(product_links)

def check_all_products():
    raw_prev = load_previous_state()
    is_first_run = raw_prev is None

    prev_products = raw_prev.get("products", {}) if raw_prev else {}
    last_price_date = raw_prev.get("last_price_alert_date", "") if raw_prev else ""

    is_daily_price_check = (TODAY_STR != last_price_date) and not is_first_run

    product_urls = get_product_links()
    print(f"🔍 전체 쇼핑몰 총 {len(product_urls)}개 부품 상태 검사 시작... (기준 날짜: {TODAY_STR})")

    current_products = {}
    stock_changes = []
    price_changes = []

    for index, url in enumerate(product_urls, 1):
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.content, "html.parser")

            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                product_name = og_title["content"].strip()
            else:
                title_tag = soup.find("h3") or soup.find("h2") or soup.find("title")
                product_name = title_tag.text.strip() if title_tag else "알 수 없는 상품"

            product_name = product_name.replace("MBS Corporation", "").strip(" :-|")
            if not product_name:
                product_name = "부품/상품"

            price = extract_price(soup)

            options = soup.find_all("option")
            available_options = []
            for option in options:
                text = option.text.strip()
                val = option.get("value", "").strip()
                if not text or val == "" or "선택" in text or "수량" in text:
                    continue
                if "[품절]" not in text and "(품절)" not in text and "품절" not in text:
                    available_options.append(text)

            is_in_stock = len(available_options) > 0

            current_products[url] = {
                "name": product_name,
                "price": price,
                "is_in_stock": is_in_stock,
                "options": available_options,
                "url": url
            }

            if not is_first_run and isinstance(prev_products, dict):
                old_item = prev_products.get(url)

                if isinstance(old_item, dict):
                    # 재고 변동 (30분 주기)
                    was_in_stock = old_item.get("is_in_stock", False)
                    if not was_in_stock and is_in_stock:
                        opt_str = f" ({', '.join(available_options)})" if available_options else ""
                        stock_changes.append({
                            "name": product_name,
                            "status": f"🟢 [재입고]{opt_str}",
                            "price": price,
                            "url": url
                        })
                    elif was_in_stock and not is_in_stock:
                        stock_changes.append({
                            "name": product_name,
                            "status": "🔴 [품절 전환]",
                            "price": price,
                            "url": url
                        })

                    # 가격 변동 (1일 1회)
                    if is_daily_price_check:
                        old_p = old_item.get("price", "")
                        if old_p != price and old_p != "가격 정보 없음" and price != "가격 정보 없음":
                            price_changes.append({
                                "name": product_name,
                                "old_price": old_p,
                                "new_price": price,
                                "url": url
                            })

            time.sleep(0.3)

        except Exception as e:
            print(f"⚠️ 개별 상품 확인 실패 ({url}): {e}")

    new_state = {
        "last_price_alert_date": TODAY_STR if is_daily_price_check or is_first_run else last_price_date,
        "products": current_products
    }
    save_current_state(new_state)

    if is_first_run:
        send_ntfy(
            "🔔 [모니터링 시스템 개설]",
            f"전체 쇼핑몰 총 {len(current_products)}개 부품 상태 등록 완료!\n• 재입고/품절: 30분마다 변동 시 통합 알림\n• 가격 변동: 1일 1회 통합 알림"
        )
        return

    if stock_changes:
        msg_lines = []
        for c in stock_changes:
            msg_lines.append(
                f"• 품목명: {c['name']}\n"
                f"  - 변경상태: {c['status']}\n"
                f"  - 가격: {c['price']}\n"
                f"  - 링크: {c['url']}"
            )
        body_text = f"총 {len(stock_changes)}개 품목의 재고 상태가 변경되었습니다:\n\n" + "\n\n".join(msg_lines)
        send_ntfy(f"📢 [재고 변동 알림] {len(stock_changes)}건 발생", body_text)
    else:
        print("ℹ️ [30분 주기] 재고 변동 없음 (알림 미발송)")

    if is_daily_price_check:
        if price_changes:
            msg_lines = []
            for p in price_changes:
                msg_lines.append(
                    f"• 품목명: {p['name']}\n"
                    f"  - 가격변동: 💰 {p['old_price']} ➔ {p['new_price']}\n"
                    f"  - 링크: {p['url']}"
                )
            body_text = f"오늘 총 {len(price_changes)}개 품목의 가격 변동이 확인되었습니다:\n\n" + "\n\n".join(msg_lines)
            send_ntfy(f"📊 [일간 가격 변동 요약] {len(price_changes)}건", body_text)
        else:
            print("ℹ️ [1일 1회] 오늘 가격 변동 없음")

if __name__ == "__main__":
    print("🚀 전체 쇼핑몰 모니터링 실행...")
    check_all_products()
    print("✨ 검사 완료.")
