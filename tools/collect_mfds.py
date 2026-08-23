#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
픽미닷 데이터 수집기 - 식품의약품안전처 기능성화장품 보고품목정보

이 파일은 GitHub Actions 안에서만 돌아간다. 사람이 직접 실행할 일은 없다.
인증키는 코드에 없고 GitHub Secrets(DATA_GO_KR_KEY)에서 읽는다.

출처: 공공데이터포털 15095680
      https://apis.data.go.kr/1471000/FtnltCosmRptPrdlstInfoService/getRptPrdlstInq
"""

import json
import os
import sys
import time
import datetime
import urllib.parse
import urllib.request
import urllib.error

API = 'https://apis.data.go.kr/1471000/FtnltCosmRptPrdlstInfoService/getRptPrdlstInq'

KEY = os.environ.get('DATA_GO_KR_KEY', '').strip()
PAGES = int(os.environ.get('PAGES', '5') or '5')     # 0 이면 전체
ROWS = int(os.environ.get('ROWS', '100') or '100')
SLEEP = float(os.environ.get('SLEEP', '0.4') or '0.4')
SINCE = int(os.environ.get('SINCE', '2021') or '2021')

OUT_DIR = 'data'
OUT_JSON = os.path.join(OUT_DIR, 'mfds.json')
OUT_REPORT = os.path.join(OUT_DIR, 'mfds_report.md')

TODAY = datetime.date.today().isoformat()

# 픽미닷 카테고리 매핑.
# 식약처 품목명은 판매명과 다를 수 있으므로 키워드는 넉넉하게 잡고,
# 몇 개가 어떻게 걸렸는지는 리포트로 확인한 뒤에 조인다.
CATS = [
    ('sun', '선크림 · 자외선차단', [
        '선크림', '썬크림', '선블록', '썬블록', '선스크린', '썬스크린',
        '자외선차단', '선쿠션', '썬쿠션', '선스틱', '썬스틱', '선젤', '선밤',
    ]),
    ('eye', '아이크림', ['아이크림', '아이 크림', '눈가', '아이세럼', '아이 세럼']),
    ('cleanse', '클렌징', ['클렌징', '클렌저', '폼클렌', '클렌즈', '워시', '세안']),
    ('mask', '마스크팩', ['마스크', '시트팩', '패드']),
    ('serum', '세럼 · 에센스 · 앰플', ['세럼', '에센스', '앰플', '앰퓰']),
    ('cream', '크림 · 로션', ['크림', '로션', '모이스처', '모이스춰']),
    ('toner', '토너 · 스킨', ['토너', '스킨', '부스터', '미스트', '플루이드']),
]

EFFECT_LABELS = [
    ('EFFECT_YN1', '미백'),
    ('EFFECT_YN2', '주름개선'),
    ('EFFECT_YN3', '자외선차단'),
]


def die(msg):
    print('')
    print('=' * 60)
    print(msg)
    print('=' * 60)
    sys.exit(1)


def fetch(page):
    """한 페이지를 받아 items 리스트와 totalCount를 돌려준다."""
    qs = urllib.parse.urlencode({
        'serviceKey': KEY,
        'pageNo': str(page),
        'numOfRows': str(ROWS),
        'type': 'json',
    })
    url = API + '?' + qs
    req = urllib.request.Request(url, headers={'User-Agent': 'pickme-collector/1.0'})
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = res.read().decode('utf-8', 'replace')

    txt = raw.lstrip()
    if not txt.startswith('{'):
        # data.go.kr 은 인증키 문제일 때 JSON 을 요청해도 XML 로 답한다.
        head = txt[:400].replace('\n', ' ')
        if 'SERVICE_KEY_IS_NOT_REGISTERED' in txt or 'SERVICE ACCESS DENIED' in txt:
            die('인증키가 아직 등록되지 않았다고 나옵니다.\n'
                '공공데이터포털은 활용신청 직후 최대 1시간 뒤에 키가 살아납니다.\n'
                '조금 뒤에 다시 실행해 주세요.\n\n응답: ' + head)
        die('JSON 이 아닌 응답이 왔습니다. 인증키를 다시 확인해 주세요.\n'
            '(마이페이지의 "일반 인증키(Decoding)" 값을 넣으셔야 합니다.)\n\n응답: ' + head)

    data = json.loads(txt)
    body = data.get('body') or {}
    header = data.get('header') or {}
    code = header.get('resultCode') or body.get('resultCode') or ''
    if code and code not in ('00', '0'):
        die('API 가 오류를 돌려줬습니다.\n코드 ' + str(code) + ' / ' +
            str(header.get('resultMsg') or body.get('resultMsg')))

    items = body.get('items') or []
    if isinstance(items, dict):
        items = items.get('item') or []
    if isinstance(items, dict):
        items = [items]
    total = int(body.get('totalCount') or 0)
    return items, total


def pick_cat(name):
    n = (name or '').replace(' ', '')
    for key, label, words in CATS:
        for w in words:
            if w.replace(' ', '') in n:
                return key, label
    return None, None


def report_year(v):
    s = str(v or '')
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return 0


def fmt_date(v):
    s = str(v or '')
    if len(s) >= 8 and s[:8].isdigit():
        return s[0:4] + '-' + s[4:6] + '-' + s[6:8]
    return ''


def main():
    if not KEY:
        die('인증키가 없습니다.\n'
            'GitHub 저장소 Settings -> Secrets and variables -> Actions 에서\n'
            'DATA_GO_KR_KEY 라는 이름으로 공공데이터포털 인증키를 넣어 주세요.')

    os.makedirs(OUT_DIR, exist_ok=True)

    print('수집을 시작합니다.')
    print('  한 페이지 ' + str(ROWS) + '건 / 요청 간격 ' + str(SLEEP) + '초')
    print('  ' + str(SINCE) + '년 이후 보고분만 남깁니다.')

    items0, total = fetch(1)
    if total <= 0:
        die('전체 건수가 0으로 왔습니다. API 응답 형식이 바뀌었을 수 있습니다.')

    last_page = (total + ROWS - 1) // ROWS
    limit = last_page if PAGES == 0 else min(PAGES, last_page)
    print('  전체 ' + str(total) + '건 / 전체 ' + str(last_page) + '페이지 중 ' +
          str(limit) + '페이지를 받습니다.')

    seen = {}
    kept = []
    scanned = 0
    dropped_cancel = 0
    dropped_old = 0
    dropped_nocat = 0
    dropped_dup = 0
    fails = 0

    page = 1
    batch = items0
    while page <= limit:
        if page > 1:
            try:
                batch, _ = fetch(page)
            except Exception as e:
                fails += 1
                print('  ! ' + str(page) + '페이지 실패: ' + str(e))
                if fails > 20:
                    die('연속 실패가 너무 많아 중단합니다. 잠시 뒤 다시 실행해 주세요.')
                time.sleep(3)
                page += 1
                continue

        for it in batch:
            scanned += 1
            if str(it.get('CANCEL_APPROVAL_YN') or '').upper() == 'Y':
                dropped_cancel += 1
                continue
            if report_year(it.get('REPORT_DATE')) < SINCE:
                dropped_old += 1
                continue

            name = (it.get('ITEM_NAME') or '').strip()
            cat, cat_label = pick_cat(name)
            if not cat:
                dropped_nocat += 1
                continue

            entp = (it.get('ENTP_NAME') or '').strip()
            dedup = name + '|' + entp
            if dedup in seen:
                dropped_dup += 1
                continue
            seen[dedup] = True

            effects = []
            for field, label in EFFECT_LABELS:
                if str(it.get(field) or '').upper() == 'Y':
                    effects.append(label)

            rec = {
                'id': str(it.get('COSMETIC_REPORT_SEQ') or '').strip(),
                'name': name,
                'entp': entp,
                'cat': cat,
                'catLabel': cat_label,
                'effects': effects,
                'reportDate': fmt_date(it.get('REPORT_DATE')),
                'src': '식품의약품안전처 기능성화장품 보고품목정보',
                'checked': TODAY,
            }

            spf = str(it.get('SPF') or '').strip()
            pa = str(it.get('PA') or '').strip()
            ph = str(it.get('ITEM_PH') or '').strip()
            wp = str(it.get('WATER_PROOFING_NAME') or '').strip()
            country = str(it.get('MANUF_COUNTRY_NAME') or '').strip()
            maker = str(it.get('MANUF_NAME') or '').strip()

            if spf:
                rec['spf'] = spf
            if pa:
                rec['pa'] = pa
            if ph:
                rec['ph'] = ph
            if wp and wp.upper() not in ('N', 'NONE'):
                rec['waterproof'] = wp
            if str(it.get('ETHANOL_OVER_YN') or '').upper() == 'Y':
                rec['ethanolOver'] = True
            if country:
                rec['country'] = country
            if maker:
                rec['maker'] = maker

            kept.append(rec)

        if page % 25 == 0 or page == limit:
            print('  ' + str(page) + '/' + str(limit) + '페이지 · 살린 것 ' +
                  str(len(kept)) + '개')
        page += 1
        if page <= limit:
            time.sleep(SLEEP)

    kept.sort(key=lambda r: (r['cat'], r.get('reportDate', ''), r['name']))

    by_cat = {}
    for r in kept:
        by_cat[r['cat']] = by_cat.get(r['cat'], 0) + 1

    by_entp = {}
    for r in kept:
        if r['entp']:
            by_entp[r['entp']] = by_entp.get(r['entp'], 0) + 1
    top_entp = sorted(by_entp.items(), key=lambda kv: -kv[1])[:15]

    out = {
        'source': '식품의약품안전처 기능성화장품 보고품목정보 (공공데이터포털 15095680)',
        'endpoint': API,
        'collectedAt': TODAY,
        'sinceYear': SINCE,
        'totalInApi': total,
        'scanned': scanned,
        'count': len(kept),
        'byCategory': by_cat,
        'items': kept,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    lines = []
    lines.append('# 식약처 수집 결과')
    lines.append('')
    lines.append('수집일 ' + TODAY + ' · ' + str(SINCE) + '년 이후 보고분 · ' +
                 str(limit) + '/' + str(last_page) + '페이지 확인')
    lines.append('')
    lines.append('훑은 것 ' + str(scanned) + '건 중 **' + str(len(kept)) + '건**을 남겼습니다. '
                 '뺀 것은 취하 ' + str(dropped_cancel) + '건, ' + str(SINCE) + '년 이전 ' +
                 str(dropped_old) + '건, 카테고리 안 걸림 ' + str(dropped_nocat) +
                 '건, 중복 ' + str(dropped_dup) + '건입니다.')
    if fails:
        lines.append('')
        lines.append('요청 실패 ' + str(fails) + '건이 있었습니다.')
    lines.append('')
    lines.append('## 카테고리별')
    lines.append('')
    lines.append('| 카테고리 | 건수 |')
    lines.append('|---|---|')
    for key, label, _w in CATS:
        lines.append('| ' + label + ' | ' + str(by_cat.get(key, 0)) + ' |')
    lines.append('')
    lines.append('## 책임판매업체 상위 15')
    lines.append('')
    lines.append('| 업체 | 건수 |')
    lines.append('|---|---|')
    for nm, c in top_entp:
        lines.append('| ' + nm + ' | ' + str(c) + ' |')
    lines.append('')
    lines.append('## 품목명 샘플 30개')
    lines.append('')
    lines.append('식약처 품목명은 판매명과 다를 수 있습니다. 아래를 보고 '
                 '사람이 알아볼 수 있는 이름인지 판단해야 합니다.')
    lines.append('')
    for r in kept[:30]:
        extra = []
        if r.get('spf'):
            extra.append('SPF' + r['spf'])
        if r.get('pa'):
            extra.append(r['pa'])
        if r.get('ph'):
            extra.append('pH ' + r['ph'])
        if r['effects']:
            extra.append('/'.join(r['effects']))
        tail = ('  (' + ' · '.join(extra) + ')') if extra else ''
        lines.append('- [' + r['catLabel'] + '] ' + r['name'] + ' — ' + r['entp'] + tail)
    lines.append('')

    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print('')
    print('끝났습니다. ' + OUT_JSON + ' 에 ' + str(len(kept)) + '개, ' +
          OUT_REPORT + ' 에 요약을 적었습니다.')


if __name__ == '__main__':
    main()
