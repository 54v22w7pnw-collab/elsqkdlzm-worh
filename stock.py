import requests
from bs4 import BeautifulSoup

# 보내주신 정확한 카테고리 URL
url = "https://mbscorp.co.kr/prod/prod_list.html?s_base_category_seq=MTY=&s_base_category_h=MTE="

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

try:
    res = requests.get(url, headers=headers, timeout=10)
    print(f"=== [진단 1] HTTP 응답 상태 코드: {res.status_code} ===")
    print(f"=== [진단 2] 수신된 응답 데이터 크기: {len(res.text)} 자 ===")
    
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 상품 상세 페이지 링크(prod_detail) 개수 체크
    prod_links = soup.find_all('a', href=lambda h: h and 'prod_detail' in h)
    print(f"=== [진단 3] 발견된 상품 상세 링크 수: {len(prod_links)} 개 ===")
    
    # 상품명 후보 태그 추출 테스트
    titles = soup.select('.title, .name, .prod_name, .tit')
    print(f"=== [진단 4] 추출된 제목 요소 수: {len(titles)} 개 ===")
    
    print("\n--- [진단 5] 수신된 HTML 앞부분 500자 ---")
    print(res.text[:500])
    
except Exception as e:
    print(f"❌ 접속 실패 오류: {e}")
