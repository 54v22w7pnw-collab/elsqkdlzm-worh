import requests
from bs4 import BeautifulSoup
import json
import os
import time

# 알림 토픽 설정 (새 토픽 이름 적용)
NTFY_TOPIC = "worhghkrdls-26"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
BASE_URL = "http://www.mbscorporation.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def send_notification(title, message, priority="default"):
    """ntfy.sh로 푸시 알림 전송 (5초 타임아웃 적용)"""
    try:
        requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": title.encode('utf-8'),
                "Priority": priority,
                "Tags": "bike,shopping_cart"
            },
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ 알림 전송 실패: {e}")

def safe_get(url, timeout=5):
    """타임아웃 적용 및 오류 발생 시 건너뛰는 안전한 GET 요청"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=timeout)
        if res.status_code == 200:
            return res
    except Exception as e:
        print(f"⚠️ 접속 실패 (건너븀): {url} - {e}")
    return None

def get_all_category_urls():
    """메인 페이지에서 카테고리 URL 추출"""
    res = safe_get(BASE_URL)
    if not res:
        return []
    
    soup = BeautifulSoup(res.text, 'html.parser')
    category_urls = set()
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'goods_list.php' in href or 'category' in href:
            if not href.startswith('http'):
                href = f"{BASE_URL}/{href.lstrip('/')}"
            category_urls.add(href)
            
    return list(category_urls)

def scrape_current_products():
    """모든 상품 상태 수집 (타임아웃 및 중복 체크 적용)"""
    products = {}
    visited_urls = set()
    category_urls = get_all_category_urls()
    
    if not category_urls:
        category_urls = [f"{BASE_URL}/goods/goods_list.php"]

    print(f"🔍 총 {len(category_urls)}개 카테고리 탐색 시작...")

    for cat_url in category_urls:
        if cat_url in visited_urls:
            continue
        visited_urls.add(cat_url)

        res = safe_get(cat_url)
        if not res:
            continue

        soup = BeautifulSoup(res.text, 'html.parser')
        
        items = soup.select('.goods_list_item, .item_box, li.goods_spec, div.goods_list_cont')
        
        for item in items:
            try:
                name_elem = item.select_one('.goods_name, .name, .prd_name')
                price_elem = item.select_one('.goods_price, .price, .prd_price')
                soldout_elem = item.select_one('.soldout, .icon_soldout, .out_of_stock')
                
                if name_elem:
                    name = name_elem.text.strip()
                    price = price_elem.text.strip() if price_elem else "가격 정보 없음"
                    is_sold_out = True if soldout_elem or "품절" in item.text else False
                    
                    products[name] = {
                        "price": price,
                        "sold_out": is_sold_out
                    }
            except Exception:
                continue

        time.sleep(0.1)

    return products

def main():
    print("🚀 쇼핑몰 수집 시작...")
    current_data = scrape_current_products()
    print(f"📦 총 {len(current_data)}개 상품 수집 완료.")

    state_file = "state.json"
    previous_data = {}

    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                previous_data = json.load(f)
        except Exception as e:
            print(f"⚠️ 기존 state.json 읽기 오류: {e}")

    if not previous_data:
        print("🎉 최초 실행: 현재 데이터 기준으로 초기 상태를 등록합니다.")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
        send_notification(
            "🔔 [모니터링 시스템 개설]",
            f"전체 쇼핑몰 총 {len(current_data)}개 상품 데이터 최초 등록 완료!\n토픽: {NTFY_TOPIC}"
        )
        return

    changes = []
    for name, info in current_data.items():
        if name in previous_data:
            prev = previous_data[name]
            if prev["sold_out"] != info["sold_out"]:
                status = "🔴 품절 전환" if info["sold_out"] else "🟢 재입고 완료!"
                changes.append(f"[{status}] {name}\n가격: {info['price']}")
            elif prev["price"] != info["price"]:
                changes.append(f"[💰 가격 변동] {name}\n기존: {prev['price']} ➡️ 변경: {info['price']}")
        else:
            status = "🔴 품절" if info["sold_out"] else "🟢 판매중"
            changes.append(f"[🆕 신상품 등록] {name} ({status})\n가격: {info['price']}")

    if changes:
        alert_msg = "\n\n".join(changes[:10])
        if len(changes) > 10:
            alert_msg += f"\n\n외 {len(changes)-10}건의 변동사항이 추가로 있습니다."
            
        send_notification("📢 [MBS 재고/가격 변동 알림]", alert_msg, priority="high")
        print("📢 변동 사항 알림 전송 완료!")
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
    else:
        print("✅ 변동 사항이 없습니다.")

if __name__ == "__main__":
    main()
