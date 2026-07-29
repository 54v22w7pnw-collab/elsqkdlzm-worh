import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re

# 알림 토픽 및 쇼핑몰 공식 URL
NTFY_TOPIC = "worhghkrdls-26"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
BASE_URL = "https://www.mbscorp.co.kr"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

# 제외할 시스템 키워드
EXCLUDE_NAMES = {
    "SOLD OUT", "SOLDOUT", "품절", "NEW", "BEST", "HOT", "RECOMMEND",
    "로그인", "장바구니", "마이페이지", "1:1문의", "전체상품", "카테고리",
    "스펙비교", "정찰가", "자세히보기", "구매하기", "공지사항", "이벤트"
}

def send_notification(title, message, priority="default"):
    """ntfy.sh 푸시 알림 전송"""
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

def safe_get(url, timeout=7):
    """안전한 HTTP GET 요청"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=timeout)
        if res.status_code == 200:
            return res
    except Exception as e:
        print(f"⚠️ 접속 실패: {url} - {e}")
    return None

def clean_text(text):
    """텍스트 정제"""
    return " ".join(text.split()).strip()

def scrape_current_products():
    """MBS Corporation 전체 상품 유연 수집"""
    products = {}
    
    # 순회할 쇼핑몰 카테고리 및 페이지 URL 목록
    target_urls = [
        f"{BASE_URL}/goods/goods_list.php",
        f"{BASE_URL}/goods/goods_list.php?cateCd=001",
        f"{BASE_URL}/goods/goods_list.php?cateCd=002",
        f"{BASE_URL}/goods/goods_list.php?cateCd=003",
        f"{BASE_URL}/goods/goods_list.php?cateCd=004",
        f"{BASE_URL}/goods/goods_list.php?cateCd=005",
    ]
    
    for page in range(1, 10):
        target_urls.append(f"{BASE_URL}/goods/goods_list.php?page={page}")

    visited_urls = set()
    print("🔍 MBS Corporation(mbscorp.co.kr) 상품 데이터 수집 시작...")

    for url in target_urls:
        if url in visited_urls:
            continue
        visited_urls.add(url)

        res = safe_get(url)
        if not res:
            continue

        soup = BeautifulSoup(res.text, 'html.parser')

        # 1. 고도몰 상품 박스 구조 수집
        containers = soup.select(
            '.item_cont, .goods_list_item, .goods_spec, .item_box, '
            'div.goods_item, li.goods_item, tr.goods_item, div.item, '
            'li.item_gallery_type, div.item_basket_type li, .goods_prj_box'
        )

        for box in containers:
            try:
                # 상품명 찾기
                name_elem = box.select_one('.item_name, .goods_name, .name, .prd_name, .item_tit, strong.name, a.item_name')
                if not name_elem:
                    continue

                name = clean_text(name_elem.text)
                for ex in EXCLUDE_NAMES:
                    name = name.replace(ex, "")
                name = name.strip(".-_[]() ")

                if not name or len(name) < 2 or name in EXCLUDE_NAMES:
                    continue

                # 가격 찾기
                price_elem = box.select_one('.item_price, .goods_price, .price, .prd_price, strong.price, .price_txt')
                if price_elem:
                    price = clean_text(price_elem.text)
                else:
                    price_match = re.search(r'([\d,]+\s*원)', box.text)
                    price = price_match.group(1) if price_match else "가격 정보 없음"

                # 품절 여부 판단
                box_text = box.text.lower()
                soldout_elem = box.select_one('.soldout, .icon_soldout, img[src*="soldout"], .sold_out')
                is_sold_out = True if (soldout_elem or "품절" in box_text or "out of stock" in box_text) else False

                if name not in products:
                    products[name] = {
                        "price": price,
                        "sold_out": is_sold_out
                    }
            except Exception:
                continue

        # 2. 백업 수집: 상품 상세페이지 링크(goods_view.php) 직접 추적
        for a_tag in soup.select('a[href*="goods_view.php"]'):
            try:
                raw_text = clean_text(a_tag.text)
                if not raw_text or len(raw_text) < 3:
                    continue

                if raw_text in EXCLUDE_NAMES or raw_text.upper() in ["SOLD OUT", "SOLDOUT"]:
                    continue

                name = raw_text
                for ex in EXCLUDE_NAMES:
                    name = name.replace(ex, "")
                
                # 가격 정규식 추출 시도
                p_match = re.search(r'([\d,]+\s*원)', name)
                if p_match:
                    name = name.replace(p_match.group(0), "")

                name = clean_text(name).strip(".-_[]() ")

                if not name or len(name) < 2 or name in EXCLUDE_NAMES:
                    continue

                if name not in products:
                    price = p_match.group(0) if p_match else "가격 정보 없음"
                    is_sold_out = "품절" in raw_text or "sold out" in raw_text.lower()
                    products[name] = {
                        "price": price,
                        "sold_out": is_sold_out
                    }
            except Exception:
                continue

        time.sleep(0.05)

    return products

def main():
    print("🚀 쇼핑몰 모니터링 시작...")
    current_data = scrape_current_products()
    print(f"📦 총 {len(current_data)}개 유효 상품 수집 완료.")

    # 최소 수집 개수 검사 (1개 이상이면 정상 진행)
    if len(current_data) == 0:
        print("❌ 상품 수집 실패")
        send_notification(
            "⚠️ [MBS 모니터링 오류]",
            "수집된 상품 수가 0개입니다. 사이트 연결 점검이 필요합니다.",
            priority="high"
        )
        return

    state_file = "state.json"
    previous_data = {}

    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                previous_data = json.load(f)
        except Exception as e:
            print(f"⚠️ 기존 state.json 읽기 오류: {e}")

    # 최초 등록이거나 이전 데이터가 "SOLD OUT" 1개뿐이었던 경우 초기화 진행
    if not previous_data or list(previous_data.keys()) == ["SOLD OUT"]:
        print("🎉 올바른 데이터로 최초 등록 진행 중...")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)

        send_notification(
            "🔔 [모니터링 시스템 개설]",
            f"MBS Corporation 총 {len(current_data)}개 상품 데이터 최초 등록 완료!\n토픽: {NTFY_TOPIC}"
        )
        return

    # 변동 사항 비교
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
