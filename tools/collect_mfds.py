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
START = int(os.environ.get('START_PAGE', '1') or '1')   # 이어받기 시작 페이지

OUT_DIR = 'data'
OUT_JSON = os.path.join(OUT_DIR, 'mfds.json')
OUT_REPORT = os.path.join(OUT_DIR, 'mfds_report.md')

TODAY = datetime.date.today().isoformat()

# 픽미닷 카테고리 나무.
#
# (대분류키, 대분류이름, 세부키, 세부이름, 걸리는 말들)
#
# 한 칸에는 한 가지 제품만 담는다. 앰플과 에센스는 사는 목적이 달라서
# 같은 칸에 두면 고르는 사람이 손해를 본다.
#
# 순서가 곧 우선순위다. 위에서부터 먼저 걸리는 칸이 임자다.
# 그래서 "클렌징 오일"이 "페이스 오일"보다 위에, "아이크림"이 "크림"보다 위에 있다.
#
# 잘게 나누는 것 자체는 공짜다. 값이 드는 쪽은 전성분과 가격을 채우는 일이므로,
# 여기서는 최대한 잘게 담아두고 앱에서는 채워진 칸만 연다.
CATS = [
    # ── 선케어 ──────────────────────────────────────────
    # 기능성화장품 보고 자료가 SPF · PA · 내수성까지 그대로 주는 분야다.
    ('sun', '선케어', 'sun_stick', '선스틱', ['선스틱', '썬스틱']),
    ('sun', '선케어', 'sun_cushion', '선쿠션', ['선쿠션', '썬쿠션', '선팩트', '썬팩트']),
    ('sun', '선케어', 'sun_spray', '선스프레이', ['선스프레이', '썬스프레이', '선미스트', '썬미스트']),
    ('sun', '선케어', 'sun_cream', '선크림 · 선로션', [
        '선크림', '썬크림', '선블록', '썬블록', '선스크린', '썬스크린',
        '자외선차단', '선로션', '썬로션', '선젤', '썬젤', '선밤', '썬밤',
        '선에센스', '선세럼', '선베이스', '톤업선', '선플루이드',
    ]),

    # ── 눈가 ────────────────────────────────────────────
    ('eye', '눈가', 'eye_patch', '아이패치', ['아이패치', '아이 패치', '눈가패치']),
    ('eye', '눈가', 'eye_serum', '아이세럼 · 아이앰플', ['아이세럼', '아이 세럼', '아이앰플', '아이에센스']),
    ('eye', '눈가', 'eye_cream', '아이크림', ['아이크림', '아이 크림', '눈가크림', '아이밤']),

    # ── 클렌징 ──────────────────────────────────────────
    # 클렌징 오일과 클렌징 폼은 대체재가 아니다. 반드시 따로 센다.
    ('cleanse', '클렌징', 'cl_oil', '클렌징 오일', ['클렌징오일', '클렌징 오일', '클렌징워터오일']),
    ('cleanse', '클렌징', 'cl_balm', '클렌징 밤', ['클렌징밤', '클렌징 밤', '클렌징셔벗']),
    ('cleanse', '클렌징', 'cl_water', '클렌징 워터 · 미셀라', ['클렌징워터', '미셀라', '리무버워터']),
    ('cleanse', '클렌징', 'cl_milk', '클렌징 크림 · 밀크', [
        '클렌징크림', '크림클렌저', '크림클렌징', '클렌징밀크', '밀크클렌저', '클렌징로션',
    ]),
    ('cleanse', '클렌징', 'cl_powder', '클렌징 파우더', ['클렌징파우더', '파우더워시', '효소세안']),
    ('cleanse', '클렌징', 'cl_bar', '세안바 (고체)', ['세안바', '클렌징바', '페이셜바', '솝바']),
    ('cleanse', '클렌징', 'cl_gel', '클렌징 젤', ['클렌징젤', '젤클렌저', '젤투폼']),
    ('cleanse', '클렌징', 'cl_foam', '클렌징 폼', [
        '클렌징폼', '폼클렌', '클렌징무스', '버블클렌', '폼',
    ]),
    # 식약처 품목명이 그냥 "클렌저"인 경우가 많다. 그 이름만으로는
    # 폼인지 젤인지 크림인지 알 수 없다. 모르는 것을 안다고 적지 않기 위해
    # 따로 담아두고, 제형은 사람이 판매 페이지에서 확인한 뒤에 옮긴다.
    ('cleanse', '클렌징', 'cl_unknown', '클렌징 (제형 확인 필요)', [
        '클렌저', '클렌징', '세안제', '페이스워시', '페이셜워시',
    ]),

    # ── 각질 · 필링 ─────────────────────────────────────
    ('peel', '각질 · 필링', 'peel_pad', '필링 패드 · 토너패드', ['토너패드', '필링패드', '데일리패드', '클리어패드']),
    ('peel', '각질 · 필링', 'peel_scrub', '스크럽 · 고마쥬', ['스크럽', '고마쥬', '고마지']),
    ('peel', '각질 · 필링', 'peel_liquid', '필링 에센스 · 필링젤', ['필링에센스', '필링젤', '각질', '필링']),

    # ── 마스크 · 팩 ─────────────────────────────────────
    ('mask', '마스크 · 팩', 'mask_sleep', '슬리핑팩', ['슬리핑팩', '수면팩', '나이트팩']),
    ('mask', '마스크 · 팩', 'mask_wash', '워시오프 팩', ['워시오프', '클레이팩', '머드팩', '모델링팩']),
    ('mask', '마스크 · 팩', 'mask_patch', '코팩 · 트러블패치', ['코팩', '트러블패치', '스팟패치', '여드름패치']),
    ('mask', '마스크 · 팩', 'mask_sheet', '시트마스크', ['시트마스크', '마스크팩', '마스크시트', '마스크']),

    # ── 토너 ────────────────────────────────────────────
    ('toner', '토너 · 스킨', 'toner_mist', '미스트', ['미스트']),
    ('toner', '토너 · 스킨', 'toner_booster', '부스터 · 프리에센스', ['부스터', '프리에센스', '퍼스트에센스', '스킨소프너']),
    # '스킨' 한 글자만으로 잡으면 스킨1004, 스킨푸드 같은 상호까지 딸려 들어온다.
    # 그래서 붙어 다니는 말로만 잡는다.
    ('toner', '토너 · 스킨', 'toner_basic', '토너 · 스킨', [
        '토너', '스킨로션', '화장수', '스킨토너', '소프너',
    ]),

    # ── 세럼류 ──────────────────────────────────────────
    # 검토자가 짚은 자리다. 앰플은 고농도 단기집중, 에센스는 수분 레이어,
    # 세럼은 그 사이. 사는 이유가 다르므로 칸을 나눈다.
    ('serum', '세럼 · 앰플', 'ser_ampoule', '앰플', ['앰플', '앰퓰', '앰풀']),
    ('serum', '세럼 · 앰플', 'ser_oil', '페이스 오일', ['페이스오일', '페이셜오일', '페이스 오일', '오일세럼']),
    ('serum', '세럼 · 앰플', 'ser_serum', '세럼', ['세럼']),
    ('serum', '세럼 · 앰플', 'ser_essence', '에센스', ['에센스']),

    # ── 크림 · 로션 ─────────────────────────────────────
    ('cream', '크림 · 로션', 'cr_gel', '수딩젤 · 젤크림', ['수딩젤', '젤크림', '워터젤', '아쿠아젤']),
    ('cream', '크림 · 로션', 'cr_balm', '밤 · 연고형', ['밤타입', '리페어밤', '카밍밤', '스킨밤']),
    ('cream', '크림 · 로션', 'cr_lotion', '로션 · 에멀전', ['에멀전', '에멀젼', '로션', '플루이드']),
    ('cream', '크림 · 로션', 'cr_cream', '크림', ['크림', '모이스처', '모이스춰', '모이스쳐']),
]

# 한 칸에 이만큼은 있어야 순위를 매긴다. 앱의 규칙과 같은 값을 쓴다.
MIN_POOL = 12


def _groups():
    """대분류를 나온 순서대로 (키, 이름)으로 돌려준다."""
    out = []
    seen = {}
    for gkey, glabel, _k, _l, _w in CATS:
        if gkey not in seen:
            seen[gkey] = True
            out.append((gkey, glabel))
    return out


EFFECT_LABELS = [
    ('EFFECT_YN1', '미백'),
    ('EFFECT_YN2', '주름개선'),
    ('EFFECT_YN3', '자외선차단'),
]


class QuotaHit(Exception):
    """공공데이터포털 하루 요청 한도에 닿았을 때.

    이건 고장이 아니라 '오늘 몫을 다 썼다'는 뜻이다.
    그래서 화를 내며 죽지 않고, 여기까지 모은 것을 저장하고 곱게 멈춘다.
    다음 날 이어서 받으면 된다.
    """
    pass


def die(msg):
    print('')
    print('=' * 60)
    print(msg)
    print('=' * 60)
    sys.exit(1)


def save_items(kept, total, scanned, last_page, next_page, done):
    """지금까지 모은 것을 파일에 적는다.

    맨 끝에서 한 번만 저장하면, 중간에 멈췄을 때 30분치를 통째로 잃는다.
    그래서 도중에도 부를 수 있게 따로 뺐다.
    next_page 를 같이 적어 두면 다음 실행이 거기서부터 이어받을 수 있다.
    """
    by_cat = {}
    for r in kept:
        by_cat[r['cat']] = by_cat.get(r['cat'], 0) + 1
    out = {
        'source': '식품의약품안전처 기능성화장품 보고품목정보 (공공데이터포털 15095680)',
        'endpoint': API,
        'collectedAt': TODAY,
        'sinceYear': SINCE,
        'totalInApi': total,
        'scanned': scanned,
        'count': len(kept),
        'lastPage': last_page,
        'nextPage': next_page,
        'done': bool(done),
        'byCategory': by_cat,
        'items': kept,
    }
    tmp = OUT_JSON + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_JSON)
    return out


def load_prev():
    """앞선 실행이 남긴 것을 읽어 온다. 없으면 빈 손으로 시작한다."""
    try:
        with open(OUT_JSON, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


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
        if ('LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS' in txt
                or 'LIMITED NUMBER OF SERVICE REQUESTS EXCEEDS' in txt
                or '<returnReasonCode>22<' in txt):
            raise QuotaHit('하루 요청 한도')
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
        msg = str(header.get('resultMsg') or body.get('resultMsg') or '')
        if str(code) in ('22', '05') or 'LIMITED' in msg.upper():
            raise QuotaHit('하루 요청 한도 (코드 ' + str(code) + ')')
        die('API 가 오류를 돌려줬습니다.\n코드 ' + str(code) + ' / ' + msg)

    items = body.get('items') or []
    if isinstance(items, dict):
        items = items.get('item') or []
    if isinstance(items, dict):
        items = [items]
    total = int(body.get('totalCount') or 0)
    return items, total


def pick_cat(name):
    """품목명을 보고 (대분류키, 대분류이름, 세부키, 세부이름)을 돌려준다.
    어느 칸에도 안 걸리면 네 개 다 None 이다."""
    n = (name or '').replace(' ', '')
    for gkey, glabel, key, label, words in CATS:
        for w in words:
            if w.replace(' ', '') in n:
                return gkey, glabel, key, label
    return None, None, None, None


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
    start = START

    # 앞선 실행이 도중에 멈췄으면 거기서부터 이어받는다.
    # 같은 페이지를 두 번 받는 것은 하루 한도를 그냥 버리는 일이다.
    prev = load_prev()
    if START > 1 and prev and prev.get('items'):
        kept = prev['items']
        scanned = int(prev.get('scanned') or 0)
        for r in kept:
            seen[r.get('id')] = True
        print('  앞선 실행에서 ' + str(len(kept)) + '건을 물려받았습니다.')
        print('  ' + str(START) + '페이지부터 이어서 받습니다.')
    elif START > 1:
        print('  ! START_PAGE 를 ' + str(START) + '로 주셨지만'
              ' 이어받을 파일이 없습니다. 1페이지부터 받습니다.')
        start = 1

    dropped_cancel = 0
    dropped_old = 0
    dropped_nocat = 0
    dropped_dup = 0
    fails = 0

    quota_stop = 0
    page = start
    batch = items0 if start == 1 else []
    while page <= limit:
        if page > 1 or start > 1:
            try:
                batch, _ = fetch(page)
            except QuotaHit as e:
                # 오늘 몫을 다 썼다는 뜻이다. 고장이 아니다.
                # 여기까지 모은 것을 저장하고 멈춘다. 내일 이어받으면 된다.
                quota_stop = page
                print('')
                print('  ' + str(page) + '페이지에서 하루 요청 한도에 닿았습니다.')
                break
            except Exception as e:
                fails += 1
                print('  ! ' + str(page) + '페이지 실패: ' + str(e))
                if fails > 20:
                    save_items(kept, total, scanned, last_page, page, done=False)
                    die('연속 실패가 너무 많아 중단합니다.\n'
                        '여기까지 모은 ' + str(len(kept)) + '건은 저장해 두었습니다.\n'
                        '다시 돌리실 때 start_page 에 ' + str(page) + ' 을 넣으면\n'
                        '앞부분을 다시 받지 않고 이어서 받습니다.')
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
            grp, grp_label, cat, cat_label = pick_cat(name)
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
                'grp': grp,
                'grpLabel': grp_label,
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
        # 도중에도 이따금 저장한다. 30분치를 한 번에 잃지 않기 위해서다.
        if page % 200 == 0:
            save_items(kept, total, scanned, last_page, page + 1, done=False)
            print('    (여기까지 저장해 두었습니다)')
        page += 1
        if page <= limit:
            time.sleep(SLEEP)

    cat_order = {}
    for i in range(len(CATS)):
        cat_order[CATS[i][2]] = i
    kept.sort(key=lambda r: (cat_order.get(r['cat'], 999),
                             r.get('reportDate', ''), r['name']))

    by_cat = {}
    for r in kept:
        by_cat[r['cat']] = by_cat.get(r['cat'], 0) + 1

    by_entp = {}
    for r in kept:
        if r['entp']:
            by_entp[r['entp']] = by_entp.get(r['entp'], 0) + 1
    top_entp = sorted(by_entp.items(), key=lambda kv: -kv[1])[:15]

    finished = (not quota_stop) and page > limit
    save_items(kept, total, scanned, last_page,
               quota_stop or page, done=finished)

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
    lines.append('열림 칸은 후보가 ' + str(MIN_POOL) + '개 이상이라 순위를 매길 수 있는 곳입니다. '
                 '식약처 자료는 뼈대일 뿐이고, 실제로 앱을 열려면 이 칸의 제품에 '
                 '가격과 전성분을 붙여야 합니다.')
    lines.append('')
    lines.append('| 대분류 | 세부 칸 | 건수 | 상태 |')
    lines.append('|---|---|---|---|')
    prev_grp = None
    for gkey, glabel, key, label, _w in CATS:
        n = by_cat.get(key, 0)
        state = '열림' if n >= MIN_POOL else ('얇음' if n else '비어 있음')
        lines.append('| ' + (glabel if gkey != prev_grp else '') + ' | ' +
                     label + ' | ' + str(n) + ' | ' + state + ' |')
        prev_grp = gkey
    lines.append('')
    grp_tot = {}
    for r in kept:
        grp_tot[r['grp']] = grp_tot.get(r['grp'], 0) + 1
    lines.append('대분류 합계 — ' + ', '.join(
        glabel + ' ' + str(grp_tot.get(gkey, 0)) + '건'
        for gkey, glabel in _groups()) + '.')
    lines.append('')
    lines.append('## 책임판매업체 상위 15')
    lines.append('')
    lines.append('| 업체 | 건수 |')
    lines.append('|---|---|')
    for nm, c in top_entp:
        lines.append('| ' + nm + ' | ' + str(c) + ' |')
    lines.append('')
    lines.append('## 칸마다 품목명 샘플 3개')
    lines.append('')
    lines.append('식약처 품목명은 허가용 이름이라 판매명과 다를 수 있습니다. '
                 '엉뚱한 칸에 들어간 것이 있는지, 사람이 알아볼 수 있는 이름인지 '
                 '여기서 눈으로 봅니다.')
    lines.append('')
    for gkey, glabel, key, label, _w in CATS:
        picks = [r for r in kept if r['cat'] == key][:3]
        if not picks:
            continue
        lines.append('**' + glabel + ' › ' + label + '** (' +
                     str(by_cat.get(key, 0)) + '건)')
        lines.append('')
        for r in picks:
            extra = []
            if r.get('spf'):
                extra.append('SPF' + r['spf'])
            if r.get('pa'):
                extra.append(r['pa'])
            if r.get('waterproof'):
                extra.append(r['waterproof'])
            if r.get('ph'):
                extra.append('pH ' + r['ph'])
            if r.get('ethanolOver'):
                extra.append('에탄올 4% 초과')
            if r['effects']:
                extra.append('/'.join(r['effects']))
            tail = ('  (' + ' · '.join(extra) + ')') if extra else ''
            lines.append('- ' + r['name'] + ' — ' + r['entp'] + tail)
        lines.append('')

    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print('')
    if not finished:
        left = last_page - (quota_stop or page) + 1
        print('')
        print('=' * 60)
        print('아직 다 못 받았습니다. 고장은 아닙니다.')
        print('')
        print('  받은 곳까지: ' + str((quota_stop or page) - 1) + '/'
              + str(last_page) + '페이지')
        print('  모아 둔 것 : ' + str(len(kept)) + '건 (저장했습니다)')
        print('  남은 것    : ' + str(left) + '페이지')
        print('')
        print('공공데이터포털 하루 요청 한도에 닿았습니다.')
        print('한도는 자정에 되돌아옵니다. 내일 같은 버튼을 다시 누르시되,')
        print('start_page 칸에 ' + str(quota_stop or page) + ' 을 넣어 주세요.')
        print('앞부분을 다시 받지 않고 이어서 받습니다.')
        print('=' * 60)
        print('')
    print('끝났습니다. ' + OUT_JSON + ' 에 ' + str(len(kept)) + '개, ' +
          OUT_REPORT + ' 에 요약을 적었습니다.')


if __name__ == '__main__':
    main()
