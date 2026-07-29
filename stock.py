import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re

# 알림 토픽 및 쇼핑몰 공식 URL 설정
NTFY_TOPIC = "worhghkrdls-26"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
BASE_URL = "https://mbscorp.co.kr"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

def scrape_current_products():
    """mbscorp.co.kr 전용 상품 및 재고 수집 로직"""
    products = {}
    
    print("🔍 MBS Corporation(mbscorp.co.kr) 상품 데이터 수집 시작...")
    
    empty_page_count = 0
    # 전체 상품 목록 페이지 순회 (page=1 ~ page=45)
    for p in range(1, 45):
        url = f"{BASE_URL}/mobile/prod/prod_list.html?page={p}"
        res = safe_get(url)
        if not res:
            continue

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 상품 상세 페이지 링크(prod_detail.html)를 포함하는 요소 탐색
        items = soup.find_all('a', href=lambda h: h and 'prod_detail.html' in h)
        
        page_items = 0
        for item in items:
            try:
                raw_text = " ".join(item.text.split())
                if not raw_text or len(raw_text) < 2:
                    continue

                # 품절 여부 확인
                is_sold_out = "품절" in raw_text or "out of stock" in raw_text.lower()

                # 가격 추출 (예: 정찰가 45,000원 또는 45,000원)
                price_match = re.search(r'(정찰가\s*[\d,]+원|[\d,]+\s*원)', raw_text)
                if price_match:
                    price = price_match.group(0)
                else:
                    price = "가격 정보 없음"

                # 상품명 정제 (가격 및 불필요 키워드 제거)
                name = raw_text
                for word in ["스펙비교", "NEW.", "NEW", "[품절]", "품절", "추천순", "인기순", "최신순"]:
                    name = name.replace(word, "")
                if price_match:
                    name = name.replace(price_match.group(0), "")
                
                name = " ".join(name.split()).strip()

                # 유효한 상품명인 경우 저장
                if name and len(name) >= 2 and name not in ["로그인", "장바구니", "마이페이지", "1:1문의"]:
                    products[name] = {
                        "price": price,
                        "sold_out": is_sold_out
                    }
                    page_items += 1
            except Exception:
                continue

        print(f"  - [{p}페이지] {page_items}개 상품 수집 완료 (누적: {len(products)}개)")

        # 3페이지 연속으로 상품이 나오지 않으면 마지막 페이지로 판단하여 탐색 종료
        if page_items == 0:
            empty_page_count += 1
            if empty_page_count >= 3:
                break
        else:
            empty_page_count = 0

        time.sleep(0.05)

    return products

def main():
    print("🚀 쇼핑몰 모니터링 시작...")
    current_data = scrape_current_products()
    print(f"📦 총 {len(current_data)}개 상품 수집 완료.")

    # 수집 실패 방지 안전장치
    if len(current_data) == 0:
        print("❌ 상품을 하나도 수집하지 못했습니다. 사이트 점검이 필요합니다.")
        return

    state_file = "state.json"
    previous_data = {}

    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                previous_data = json.load(f)
        except Exception as e:
            print(f"⚠️ 기존 state.json 읽기 오류: {e}")

    # 최초 실행인 경우
    if not previous_data:
        print("🎉 최초 등록 진행 중...")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
        send_notification(
            "🔔 [모니터링 시스템 개설]",
            f"MBS Corporation 전체 {len(current_data)}개 상품 데이터 최초 등록 완료!\n토픽: {NTFY_TOPIC}"
        )
        return

    # 변동 사항 확인
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
