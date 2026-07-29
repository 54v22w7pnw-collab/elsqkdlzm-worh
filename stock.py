import requests
from bs4 import BeautifulSoup
import json
import os
import re
from urllib.parse import urljoin

NTFY_TOPIC = "worhghkrdls-26"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

BASE_URL = "https://mbscorp.co.kr"
DEFAULT_CATEGORY_URL = "https://mbscorp.co.kr/prod/prod_list.html?s_base_category_seq=MTY=&s_base_category_h=MTE="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
}

EXCLUDE_NAMES = {
    "SOLD OUT", "SOLDOUT", "품절", "NEW", "BEST", "HOT",
    "로그인", "장바구니", "마이페이지", "1:1문의", "전체상품", "카테고리",
    "구매하기", "공지사항", "이벤트", "자세히보기", "메인페이지"
}

def send_notification(title, message, priority="default"):
    """ntfy 알림 전송"""
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

def clean_text(text):
    return " ".join(text.split()).strip()

def get_all_category_urls():
    """사이트 메뉴에서 모든 카테고리 URL 자동 추출"""
    category_urls = set()
    category_urls.add(DEFAULT_CATEGORY_URL)

    try:
        res = requests.get(BASE_URL, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')

            for a in soup.find_all('a', href=lambda h: h and 'prod_list.html' in h):
                full_url = urljoin(BASE_URL, a['href'])
                category_urls.add(full_url)

        print(f"📁 총 {len(category_urls)}개의 카테고리 URL 자동 발견 완료.")
    except Exception as e:
        print(f"⚠️ 카테고리 자동 추출 중 오류 발생 (기본 URL로 진행): {e}")

    return list(category_urls)

def scrape_current_products():
    products = {}
    target_urls = get_all_category_urls()

    for url in target_urls:
        print(f"🔍 카테고리 수집 중: {url}")
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                print(f"⚠️ 접속 실패 (상태 코드: {res.status_code})")
                continue

            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')

            detail_links = soup.find_all('a', href=lambda h: h and 'prod_detail' in h)

            for a in detail_links:
                card = a.find_parent(['li', 'div', 'tr', 'td']) or a
                raw_text = clean_text(card.text)
                
                if not raw_text or len(raw_text) < 2:
                    continue

                # 1. 상품명 추출
                img = card.find('img')
                img_alt = img.get('alt', '').strip() if img else ""

                lines = [line.strip() for line in card.text.split('\n') if line.strip()]
                possible_name = ""
                for line in lines:
                    line_clean = clean_text(line)
                    if line_clean in EXCLUDE_NAMES or re.search(r'[\d,]+\s*원', line_clean):
                        continue
                    if len(line_clean) >= 2:
                        possible_name = line_clean
                        break

                if not possible_name and img_alt:
                    possible_name = img_alt

                if not possible_name or possible_name in EXCLUDE_NAMES:
                    continue

                name = possible_name
                for ex in EXCLUDE_NAMES:
                    name = name.replace(ex, "")
                name = name.strip(".-_[]() ")

                if len(name) < 2:
                    continue

                # 2. 가격 추출
                price_match = re.search(r'([\d,]+\s*원)', raw_text)
                price = price_match.group(1) if price_match else "가격 정보 없음"

                # 3. 정밀 품절 검사 (_off 이미지 예외 처리)
                is_sold_out = False
                
                soldout_imgs = card.select('img[src*="soldout"], img[src*="sold_out"], img[alt*="품절"]')
                for img_tag in soldout_imgs:
                    src = img_tag.get('src', '').lower()
                    alt = img_tag.get('alt', '').lower()
                    style = img_tag.get('style', '').replace(' ', '').lower()

                    if 'off' in src or 'off' in alt:
                        continue
                    if 'display:none' in style or 'visibility:hidden' in style:
                        continue

                    is_sold_out = True
                    break

                if "품절" in price or "sold out" in price.lower():
                    is_sold_out = True

                if name not in products:
                    products[name] = {
                        "price": price,
                        "sold_out": is_sold_out
                    }

        except Exception as e:
            print(f"❌ 크롤링 에러 ({url}): {e}")

    return products

def main():
    print("🚀 모니터링 스크립트 실행...")
    current_data = scrape_current_products()
    print(f"📦 전체 카테고리 통합 총 {len(current_data)}개 유효 상품 수집 완료.")

    if len(current_data) == 0:
        print("❌ 수집된 상품이 0개입니다.")
        send_notification(
            "⚠️ [MBS 모니터링 오류]",
            "수집된 상품 수가 0개입니다. 점검이 필요합니다.",
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
            print(f"⚠️ state.json 읽기 에러: {e}")

    # state.json 파일이 아예 없을 때만 초기 등록 진행
    if not previous_data:
        print("🎉 전체 카테고리 데이터 통합 초기 등록 중...")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)

        send_notification(
            "🔔 [MBS 전체 카테고리 모니터링 개설]",
            f"모든 카테고리 자동 수집 완료!\n총 {len(current_data)}개 상품 데이터 등록 완료."
        )
        return

    # 실시간 데이터 변동 비교 로직
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
            changes.append(f"[🆕 신상품] {name} ({status})\n가격: {info['price']}")

    if changes:
        alert_msg = "\n\n".join(changes[:10])
        if len(changes) > 10:
            alert_msg += f"\n\n외 {len(changes)-10}건 변동 발생"

        send_notification("📢 [MBS 재고/가격 변동]", alert_msg, priority="high")

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
    else:
        print("✅ 변동 사항이 없습니다.")

if __name__ == "__main__":
    main()
