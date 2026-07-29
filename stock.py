name: MBS Stock Monitor

on:
  schedule:
    # 매 3시간마다 실행 (UTC 기준 0시, 3시, 6시... -> 한국 시간 기준 오전 9시, 낮 12시, 오후 3시...)
    - cron: '0 */3 * * *'
  workflow_dispatch: # Actions 탭에서 수동 실행 버튼 제공

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4

      - name: Run script
        run: python stock.py

      - name: Commit and push changes
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add state.json
          git diff --quiet && git diff --staged --quiet || (git commit -m "Update state" && git push)
