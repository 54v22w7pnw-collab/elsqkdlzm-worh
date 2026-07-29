import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re

# 알림 토픽 및 쇼핑몰 공식 URL
NTFY_TOPIC = "worhghkrdls-26"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
BASE_URL = "https://mbscorp.co.kr"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# 제외할 시스템 키워드 및 불필요 문구
EXCLUDE_KEYWORDS = [
    "SOLD OUT", "SOLDOUT", "품절", "NEW", "BEST", "HOT", "RECOMMEND",
    "로그인", "장바구니", "마이페이지", "1:1문의", "전체상품", "카테고리",
    "스펙비교", "픽업", "MORE", "DISCOVER MORE", "WHERE TO BUY", "FIND STORE",
    "MAGAZINE", "FAQ", "정품등록", "자료실", "품질보증안내", "제품비교", "커스텀 주문",
    "쿠폰안내", "비회원 주문조회", "이용약관", "개인정보취급방침", "ABOUT MBS", "세일"
]

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
    """공백 및 특수 제어문자 정제"""
    return " ".join(text.split()).strip()

def parse_product_from_text(raw_text):
    """
    텍스트 블록에서 정규식을 이용해 [상품명], [가격], [품절여부]를 정확히 정밀 추출
    """
    if not raw_text or len(raw_text) < 3:
        return None, None, False

    text = clean_text(raw_text)

    # 1. 품절 여부 체크
    is_sold_out = any(kw in text.upper() for kw in ["SOLD OUT", "SOLDOUT", "품절", "OUT OF STOCK"])

    # 2. 가격 추출 (예: 1,160,000원, 45,000원 등)
    price_match = re.search(r'([\d,]+\s*원)', text)
    if not price_match:
        return None, None, False
    
    price_str = price_match.group(1).strip()

    # 3. 상품명 정제 (가격 및 불필요 배지/키워드 완벽 제거)
    name = text
    name = re.sub(r'정찰가\s*[\d,]+\s*원', '', name)
    name = re.sub(r'[\d,]+\s*원', '', name)
    name = re.sub(r'\[\d+%\s*세일\]', '', name)
    name = re.sub(r'\[\d+%\]', '', name)

    for kw in EXCLUDE_KEYWORDS:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        name = pattern.sub('', name)

    name = clean_text(name).strip(".-_[]() ")

    # 4. 검증: 남아있는 상품명이 유효한지 체크
    if not name or len(name) < 2 or name.upper() in [k.upper() for k in EXCLUDE_KEYWORDS]:
        return None, None, False

    return name, price_str, is_sold_out

def scrape_current_products():
    """MBS Corporation 전체 카테고리 교차 정밀 수집"""
    products = {}
    
    # 주요 메인 및 브랜드 시드 URL
    seed_urls = [
        f"{BASE_URL}/",
        f"{BASE_URL}/elfama/",
        f"{BASE_URL}/vittoria/",
        f"{BASE_URL}/dtswiss/",
        f"{BASE_URL}/gaerne/",
        f"{BASE_URL}/superb/",
    ]
    
    # 페이지네이션 수집 (1 ~ 15 페이지)
    for p in range(1, 16):
        seed_urls.append(f"{BASE_URL}/mobile/prod/prod_list.html?page={p}")
        seed_urls.append(f"{BASE_URL}/goods/goods_list.php?page={p}")

    print(f"🔍 총 {len(seed_urls)}개 쇼핑몰 경로 탐색 중...")

    for url in seed_urls:
        res = safe_get(url)
        if not res:
            continue

        soup = BeautifulSoup(res.text, 'html.parser')

        # 1) 상품 링크 태그(<a>) 수집
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href', '')
            if any(k in href for k in ['goods_view', 'prod_detail', 's_base_brand', 's_base_category']):
                name, price, sold_out = parse_product_from_text(a_tag.text)
                if name and price and name not in products:
                    products[name] = {"price": price, "sold_out": sold_out}

        # 2) 상품 그리드 카드(.item_cont, .goods_spec 등) 수집
        containers = soup.select(
            '.item_cont, .goods_list_item, .goods_spec, .item_box, '
            'div.goods_item, li.goods_item, tr.goods_item, div.prod_item'
        )

        for box in containers:
            has_soldout_badge = bool(box.select_one('.soldout, .icon_soldout, img[src*="soldout"]'))
            name, price, sold_out = parse_product_from_text(box.text)
            if name and price:
                if has_soldout_badge:
                    sold_out = True
                if name not in products:
                    products[name] = {"price": price, "sold_out": sold_out}

        time.sleep(0.05)

    return products

def main():
    print("🚀 쇼핑몰 모니터링 시작...")
    current_data = scrape_current_products()
    print(f"📦 총 {len(current_data)}개 유효 상품 수집 완료.")

    # 수집 개수 유효성 검사 (5개 미만 시 오류 알림 후 중단)
    if len(current_data) < 5:
        print("❌ 정상적인 상품 데이터 수집에 실패했습니다.")
        send_notification(
            "⚠️ [MBS 모니터링 오류]",
            f"수집된 상품 수({len(current_data)}개)가 정상 기준에 미달합니다. 점검이 필요합니다.",
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

    # 이전 데이터가 없거나, "SOLD OUT" 1개만 잘못 들어있던 경우 자동 초기화
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
