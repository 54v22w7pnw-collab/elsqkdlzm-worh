import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

CATEGORY_URLS = [
    "https://mbscorp.co.kr/prod/prod_list.html?s_base_category_seq=MTY=&s_base_category_h=NDU="
]
NTFY_TOPIC = "elsqkdlzm-worh26"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

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

def get_product_links():
    product_links = set()
    for cat_url in CATEGORY_URLS:
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
        except Exception as e:
            print(f"⚠️ 카테고리 로딩 중 오류: {e}")
    return list(product_links)

def check_all_products():
    product_urls = get_product_links()
    print(f"🔍 총 {len(product_urls)}개 부품 검사 시작...")

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

            options = soup.find_all("option")
            available_options = []

            for option in options:
                text = option.text.strip()
                val = option.get("value", "").strip()
                if not text or val == "" or "선택" in text or "수량" in text:
                    continue
                if "[품절]" not in text and "(품절)" not in text and "품절" not in text:
                    available_options.append(text)

            if available_options:
                print(f"🟢 [{index}/{len(product_urls)}] 입고 감지! ({product_name})")
                opt_str = "\n".join(available_options)
                send_ntfy(
                    f"🎉 [입고 알림] {product_name}",
                    f"구매 가능 옵션:\n{opt_str}\n\n👉 링크: {url}"
                )
            else:
                print(f"🔴 [{index}/{len(product_urls)}] 품절: {product_name[:20]}...")

            time.sleep(0.3)

        except Exception as e:
            print(f"⚠️ 개별 상품 확인 실패 ({url}): {e}")

if __name__ == "__main__":
    print("🚀 GitHub Actions 모니터링 실행...")
    check_all_products()
    print("✨ 검사 완료.")
