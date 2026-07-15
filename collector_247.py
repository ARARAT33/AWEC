name: AWEC Continuous Link Collector

on:
  push:
    branches:
      - main
  schedule:
    - cron: '0 */5 * * *' # Ամեն 5 ժամը մեկ
  workflow_dispatch:      # Ձեռքով թողարկելու հնարավորություն

concurrency:
  group: aw_crawler_group
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  crawl:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'

      - name: Install System Dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y sqlite3 jq curl pv

      - name: Install Python Requirements
        run: |
          python -m pip install --upgrade pip
          python -m pip install aiohttp internetarchive beautifulsoup4 requests

      - name: Download Last DB with Progress (%)
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          echo "🔄 Փնտրում ենք վերջին տվյալների բազան..."
          RELEASE_DATA=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
            https://api.github.com/repos/${{ github.repository }}/releases/latest || true)
          
          DOWNLOAD_URL=$(echo "$RELEASE_DATA" | jq -r '.assets[] | select(.name=="links.db") | .url' 2>/dev/null || echo "")
          
          if [ -n "$DOWNLOAD_URL" ] && [ "$DOWNLOAD_URL" != "null" ]; then
            echo "📥 Գտնվեց նախորդ բազան։ Ներբեռնում ենք..."
            curl -L -H "Authorization: token $GITHUB_TOKEN" \
                 -H "Accept: application/octet-stream" \
                 -o links.db "$DOWNLOAD_URL" --progress-bar
            echo "✅ Ներբեռնումն ավարտվեց։"
          else
            echo "ℹ️ Նախորդ բազա չգտնվեց։ Կստեղծվի նորը..."
          fi

      - name: Check and Repair SQLite Database with Status (%)
        run: |
          if [ -f "links.db" ]; then
            echo "🛠️ Ստուգում ենք բազայի ամբողջականությունը..."
            INTEGRITY=$(sqlite3 links.db "PRAGMA integrity_check;" 2>&1 || echo "error")
            
            if [ "$INTEGRITY" != "ok" ] || [[ "$INTEGRITY" == *"error"* ]] || [[ "$INTEGRITY" == *"malformed"* ]]; then
              echo "⚠️ Բազան վնասված է։ Սկսում ենք բուժման գործընթացը..."
              
              OLD_ROWS=$(sqlite3 links.db "SELECT COUNT(*) FROM urls" 2>/dev/null || echo "0")
              
              mv links.db links_corrupted.db
              sqlite3 links_corrupted.db ".recover" | sqlite3 links.db
              
              if [ -f "links.db" ]; then
                NEW_ROWS=$(sqlite3 links.db "SELECT COUNT(*) FROM urls" 2>/dev/null || echo "0")
                
                if [ "$OLD_ROWS" -gt 0 ]; then
                  RECOVERY_RATE=$(( (NEW_ROWS * 100) / OLD_ROWS ))
                else
                  RECOVERY_RATE=100
                fi
                echo "🎉 Բուժումն ավարտվեց։ Վերականգնվել է տվյալների $RECOVERY_RATE% -ը ($NEW_ROWS / $OLD_ROWS հղում)։"
                rm -f links_corrupted.db
              else
                echo "🚨 Բուժումը ձախողվեց։ Ստեղծվում է դատարկ բազա..."
                rm -f links_corrupted.db
              fi
            else
              echo "✅ Բազան 100% առողջ է, բուժման կարիք չկա։"
            fi
          fi

      - name: Run AWEC Planetary Crawler (5 Hours Run Limit)
        run: |
          echo "🚀 Սկսում ենք սարդի աշխատանքը 5 ժամով..."
          
          # Միացնում ենք քո սարդը ֆոնային ռեժիմով (background)
          python collector_247.py &
          SPIDER_PID=$!
          
          echo "🕷️ Սարդը միացավ PID $SPIDER_PID-ով։ Սպասում ենք 5 ժամ..."
          
          # Սպասում ենք 5 ժամ (18000 վայրկյան)
          sleep 18000
          
          echo "⏰ 5 ժամը լրացավ։ Կանգնեցնում ենք սարդին..."
          # Ուղարկում ենք SIGINT (Ctrl+C-ի էֆեկտ), որպեսզի Python-ի finally բլոկը ապահով պահպանի տվյալները
          kill -2 $SPIDER_PID
          
          # Սպասում ենք, որ պրոցեսը լրիվ ավարտվի և բազան փակվի
          wait $SPIDER_PID || true
          echo "✅ Սարդը հաջողությամբ կանգնեցվեց։"

      - name: Export DB to Plain Text (Final)
        if: always()
        run: |
          python -c "
          import sqlite3
          import os
          if os.path.exists('links.db'):
              try:
                  conn = sqlite3.connect('links.db')
                  cursor = conn.cursor()
                  cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='urls'\")
                  if cursor.fetchone():
                      cursor.execute('SELECT url FROM urls')
                      urls = cursor.fetchall()
                      with open('links.txt', 'w', encoding='utf-8') as f:
                          for u in urls:
                              f.write(u[0] + '\n')
                      print(f'🎉 Exported {len(urls)} links.')
                  else:
                      print('Table urls does not exist!')
                  conn.close()
              except Exception as e:
                  print('Export failed:', e)
          else:
              print('links.db not found!')
          "

      - name: Prepare Unique Release Tag and Filename (Final)
        if: always()
        id: prep
        run: |
          if [ -f "links.db" ]; then
            COUNT=$(sqlite3 links.db "SELECT COUNT(*) FROM urls" 2>/dev/null || echo "0")
          else
            COUNT=0
          fi
          
          TIMESTAMP=$(date -d '+4 hours' +'%Y%m%d_%H%M%S')
          TAG_NAME="v-${TIMESTAMP}"
          ARCHIVE_FILENAME="${TIMESTAMP}_links_${COUNT}.db"
          
          echo "COUNT=$COUNT" >> $GITHUB_OUTPUT
          echo "TAG_NAME=$TAG_NAME" >> $GITHUB_OUTPUT
          echo "TIMESTAMP=$TIMESTAMP" >> $GITHUB_OUTPUT
          echo "ARCHIVE_FILENAME=$ARCHIVE_FILENAME" >> $GITHUB_OUTPUT
          
          if [ -f "links.db" ]; then
            cp links.db "$ARCHIVE_FILENAME"
          fi

      - name: Create New GitHub Release and Upload Unique Assets (Final)
        if: always() && steps.prep.outputs.COUNT != '0' && steps.prep.outputs.COUNT != ''
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TAG: ${{ steps.prep.outputs.TAG_NAME }}
        run: |
          echo "🔄 Ստեղծում ենք վերջնական GitHub Release..."
          
          RELEASE_ID=$(curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
            -d "{\"tag_name\":\"$TAG\",\"name\":\"AWEC Run $TAG\",\"body\":\"Successfully collected ${{ steps.prep.outputs.COUNT }} links.\",\"draft\":false,\"prerelease\":false}" \
            https://api.github.com/repos/${{ github.repository }}/releases | jq -r '.id')
          
          if [ "$RELEASE_ID" != "null" ] && [ -n "$RELEASE_ID" ]; then
            # -T-ի շնորհիվ ֆայլը կվերբեռնվի սթրիմով՝ լիովին բացառելով 'out of memory' սխալը
            curl -# -X POST \
              -H "Authorization: token $GITHUB_TOKEN" \
              -H "Content-Type: application/octet-stream" \
              -T links.db \
              "https://uploads.github.com/repos/${{ github.repository }}/releases/$RELEASE_ID/assets?name=links.db"
            
            curl -# -X POST \
              -H "Authorization: token $GITHUB_TOKEN" \
              -H "Content-Type: text/plain" \
              -T links.txt \
              "https://uploads.github.com/repos/${{ github.repository }}/releases/$RELEASE_ID/assets?name=links.txt"
          fi

      - name: Upload Snapshot to Internet Archive (Final)
        if: always() && steps.prep.outputs.COUNT != '0' && steps.prep.outputs.ARCHIVE_FILENAME != ''
        env:
          IA_ACCESS_KEY: ${{ secrets.IA_ACCESS_KEY }}
          IA_SECRET_KEY: ${{ secrets.IA_SECRET_KEY }}
        run: |
          FILENAME="${{ steps.prep.outputs.ARCHIVE_FILENAME }}"
          echo "📤 Ուղարկում ենք Internet Archive: $FILENAME"
          mkdir -p ~/.config
          cat <<EOF > ~/.config/ia.ini
          [s3]
          access = $IA_ACCESS_KEY
          secret = $IA_SECRET_KEY
          EOF
          
          ia upload awec_links_awe_o.s "$FILENAME" \
            --metadata="title:AWEC Harvest $FILENAME" \
            --metadata="mediatype:data" \
            --metadata="collection:opensource"

      - name: Wait 30s and Trigger Next Loop Automatically
        if: always()
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          echo "💤 Սպասում ենք 30 վայրկյան..."
          sleep 30
          
          RUNS_COUNT=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
            "https://api.github.com/repos/${{ github.repository }}/actions/workflows/awec-247.yml/runs?status=queued" \
            | jq '.total_count')
          
          if [ "$RUNS_COUNT" -eq 0 ] || [ -z "$RUNS_COUNT" ]; then
            echo "🔄 Կանչում ենք հաջորդ ցիկլը..."
            curl -X POST \
              -H "Authorization: token $GITHUB_TOKEN" \
              -H "Accept: application/vnd.github.v3+json" \
              https://api.github.com/repos/${{ github.repository }}/actions/workflows/awec-247.yml/dispatches \
              -d '{"ref":"main"}'
          else
            echo "ℹ️ Հերթում արդեն կա սպասող աշխատանք։"
          fi