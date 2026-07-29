name: MBS Stock Monitor

on:
  schedule:
    - cron: '*/30 * * * *'  # 30분마다 자동 실행
  workflow_dispatch:        # 수동으로 실행해볼 수 있는 버튼 생성

jobs:
  check-stock:
    runs-on: ubuntu-latest

    steps:
      - name: 코드 가져오기
        uses: actions/checkout@v4

      - name: 파이썬 설정
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: 필요한 라이브러리 설치
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4

      - name: 재고 확인 스크립트 실행
        run: python stock.py
