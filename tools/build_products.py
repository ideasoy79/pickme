#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
픽미닷 상품 파일 만들기 — 정제 결과를 앱이 읽는 products.json 으로 합친다.

이 단계에는 AI가 없다. 규칙만 있다.
어떤 제품이 위로 올라가고 무엇이 화면에 적히는지는 사람이 읽을 수 있는
규칙이어야 하기 때문이다.

--------------------------------------------------------------------
두 종류의 제품을 다르게 다룬다.
--------------------------------------------------------------------
확인분(verified)
  사람이 판매 페이지에서 가격과 전성분까지 눈으로 확인한 것.
  점수를 매기고 순위를 낼 수 있다. 지금은 21개뿐이다.

목록분(listed)
  식약처 보고 자료만 있는 것. 가격도 전성분도 없다.
  대신 SPF·PA·내수성·pH·에탄올·미백/주름 인정은 국가 자료라 확실하다.
  그래서 순위는 매기지 않고, 조건에 맞는 것을 찾아 주는 데만 쓴다.

이 둘을 섞어서 한 줄로 세우지 않는다. 섞으면 앱이 모르는 것을
아는 척하게 된다. 화면에도 어느 쪽인지 적는다.
--------------------------------------------------------------------
"""

import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_mfds import CATS  # noqa: E402

MFDS = os.path.join('data', 'mfds.json')
REFINED = os.path.join('data', 'refined.json')
CURRENT = 'products.json'
OUT = 'products.json'
REPORT = os.path.join('data', 'build_report.md')

TODAY = datetime.date.today().isoformat()

MIN_POOL = 12
# 한 칸에 목록분을 이만큼까지만 싣는다. 앱 파일이 무거워지면
# 휴대폰에서 늦게 열린다. 늦게 열리는 앱은 안 쓴다.
CAP_PER_CAT = int(os.environ.get('CAP_PER_CAT', '30') or '30')
# 파일이 이보다 커지면 경고한다. 데이터가 늘면 대분류별로 쪼개야 한다.
WARN_KB = 700

CAT_INFO = {}
for _g, _gl, _k, _l, _w in CATS:
    CAT_INFO[_k] = (_g, _gl, _l)

# 칸마다 "이건 꼭 보고 산다"는 기준. 화면 배지로 나간다.
# 값이 있는 것만 나가므로, 없으면 아무것도 안 적힌다.
# 사람이 확인한 21개는 옛 방식(대분류 + seg + form)으로 적혀 있다.
# 이것을 새 세부 칸으로 옮긴다. 손으로 확인한 자료를 버리지 않기 위해서다.
VERIFIED_CELL = {
    ('cleanse', 'bar'): 'cl_bar',
    ('cleanse', 'foam'): 'cl_foam',
    ('cleanse', 'gel'): 'cl_gel',
    ('cleanse', 'cream'): 'cl_milk',
    ('cleanse', 'oil'): 'cl_oil',
    ('cleanse', 'balm'): 'cl_balm',
    ('cleanse', 'water'): 'cl_water',
    ('cleanse', 'powder'): 'cl_powder',
    ('cleanse', 'peel'): 'peel_liquid',
    ('cleanse', 'pad'): 'peel_pad',
}

SPEC_BY_GROUP = {
    'sun': ['spf', 'pa', 'waterproof'],
    'eye': ['effects', 'ph'],
    'cleanse': ['ph', 'ethanol'],
    'peel': ['ph', 'ethanol'],
    'mask': ['effects', 'ethanol'],
    'toner': ['ph', 'ethanol'],
    'serum': ['effects', 'ph'],
    'cream': ['effects', 'ph'],
}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# 판매 링크는 파일에 넣지 않는다. 앱이 브랜드와 제품명으로 그때그때 만든다.
# 링크 한 줄이 120바이트인데 제품이 천 개면 120KB다. 그 값을 치를 이유가 없다.
# 특정 판매 페이지 주소를 박아 넣지 않는 이유도 있다. 그런 주소는 품절되면
# 죽고, 죽은 링크는 앱을 못 믿게 만든다. 검색 링크는 이름만 맞으면 산다.


def specs_for(grp, r):
    """식약처 원본에서 화면에 적을 값을 뽑는다. 값이 없으면 안 적는다."""
    want = SPEC_BY_GROUP.get(grp) or []
    out = []
    for w in want:
        if w == 'spf' and r.get('spf'):
            out.append({'k': '자외선차단지수', 'v': 'SPF ' + str(r['spf'])})
        elif w == 'pa' and r.get('pa'):
            out.append({'k': 'UVA 차단등급', 'v': str(r['pa'])})
        elif w == 'waterproof' and r.get('waterproof'):
            out.append({'k': '내수성', 'v': str(r['waterproof'])})
        elif w == 'ph' and r.get('ph'):
            out.append({'k': 'pH', 'v': str(r['ph'])})
        elif w == 'ethanol':
            if r.get('ethanolOver'):
                out.append({'k': '에탄올', 'v': '4% 초과 함유'})
        elif w == 'effects' and r.get('effects'):
            out.append({'k': '기능성 인정', 'v': ' · '.join(r['effects'])})
    return out


def watch_for(grp, r):
    """주의점을 만든다. 전부 식약처 표기에서 나온 말이다.
    없는 사실을 만들어 내지 않는다. 할 말이 없으면 빈 문자열이다."""
    bits = []
    if r.get('ethanolOver'):
        bits.append('에탄올이 4%를 넘게 들어 있다고 보고된 제품입니다. '
                    '눈가에 닿으면 시릴 수 있고, 건조함을 느끼는 분은 '
                    '피하는 편이 낫습니다.')
    ph = str(r.get('ph') or '').strip()
    try:
        phv = float(ph)
        if phv >= 9:
            bits.append('pH ' + ph + '으로 알칼리 쪽입니다. '
                        '세정력은 좋지만 당김이 있을 수 있습니다.')
        elif phv and phv <= 3.5:
            bits.append('pH ' + ph + '으로 산성이 강한 편입니다. '
                        '처음 쓰신다면 사용 횟수를 줄여 시작하세요.')
    except ValueError:
        pass
    if grp == 'sun' and not r.get('waterproof'):
        bits.append('내수성 표기가 없습니다. 물놀이나 땀이 많은 날에는 '
                    '자주 덧발라야 합니다.')
    if not r.get('effects'):
        bits.append('미백·주름개선 같은 기능성 인정을 받은 항목이 없습니다. '
                    '보습이나 사용감 위주로 보시는 게 맞습니다.')
    return ' '.join(bits)


def good_for(grp, r, note):
    # 숫자는 specs 칸에 이미 나가므로 여기서 되풀이하지 않는다.
    # 같은 말을 두 번 적으면 화면만 길어지고 파일만 무거워진다.
    bits = []
    if r.get('effects'):
        bits.append('식약처 ' + ' · '.join(r['effects']) + ' 인정 제품입니다.')
    else:
        bits.append('식약처에 기능성화장품으로 보고된 제품입니다.')
    if note:
        bits.append('품목명에 ' + note + '가 있습니다.')
    return ' '.join(bits)


def main():
    mf = load_json(MFDS, None)
    if not mf:
        print('! ' + MFDS + ' 이 없습니다. 수집을 먼저 돌려 주세요.')
        sys.exit(1)
    rows = mf.get('items') if isinstance(mf, dict) else mf

    rf = load_json(REFINED, {})
    refined = rf.get('items') or {}
    if not refined:
        print('! ' + REFINED + ' 이 비어 있습니다. 정제를 먼저 돌려 주세요.')
        sys.exit(1)

    cur = load_json(CURRENT, {})
    verified = []
    unmapped = []
    for p in (cur.get('products') or []):
        # 사람이 확인한 것은 무슨 일이 있어도 지우지 않는다.
        p['tier'] = 'verified'
        # 대분류는 cat, 세부 칸은 cell 로 통일한다.
        # 옛 파일에는 cell 이 없으므로 form 을 보고 채운다.
        if not p.get('cell'):
            cell = VERIFIED_CELL.get((p.get('cat'), p.get('form')))
            if not cell:
                cell = VERIFIED_CELL.get((p.get('cat'), p.get('seg')))
            if cell:
                p['cell'] = cell
            else:
                # 어느 칸인지 못 정하면 비워 둔다. 아무 칸에나 넣지 않는다.
                unmapped.append(p.get('brand', '') + ' ' + p.get('name', ''))
        verified.append(p)
    print('확인분 ' + str(len(verified)) + '개를 그대로 둡니다.')
    if unmapped:
        print('! 세부 칸을 못 정한 확인분 ' + str(len(unmapped)) + '개:')
        for u in unmapped[:10]:
            print('    - ' + u)

    by_id = {}
    for r in rows:
        by_id[r.get('id')] = r

    # 목록분을 만든다.
    buckets = {}
    for pid, v in refined.items():
        if not v.get('retail'):
            continue
        r = by_id.get(pid)
        if not r:
            continue
        cat = v.get('cat') or ''
        if cat not in CAT_INFO:
            # 제형을 모르면 싣지 않는다. 모르는 채로 칸에 넣으면
            # 폼을 찾는 사람에게 젤을 내밀게 된다.
            continue
        grp, grp_label, cat_label = CAT_INFO[cat]  # noqa: F841
        brand = v.get('brand') or ''
        title = v.get('title') or r.get('name') or ''
        item = {
            'id': 'm' + str(pid),
            'tier': 'listed',
            'cat': grp,
            'cell': cat,
            'brand': brand,
            'name': title,
            'entp': r.get('entp') or '',
            'specs': specs_for(grp, r),
            'good': good_for(grp, r, v.get('note')),
            'watch': watch_for(grp, r),
            'reportDate': r.get('reportDate') or '',
            # 출처는 제품마다 적지 않고 파일 위쪽 sources 를 가리킨다.
            # 같은 문장을 천 번 적으면 그것만 40KB다.
            'src': 'mfds',
            'checked': r.get('checked') or TODAY,
        }
        for k in ('spf', 'pa', 'waterproof', 'ph', 'country'):
            if r.get(k):
                item[k] = r[k]
        if r.get('ethanolOver'):
            item['ethanolOver'] = True
        if r.get('effects'):
            item['effects'] = r['effects']
        buckets.setdefault(cat, []).append(item)

    listed = []
    counts = {}
    for _g, _gl, key, _l, _w in CATS:
        lot = buckets.get(key) or []
        # 값이 많이 적힌 것부터. 화면에 보여 줄 게 많은 쪽이 쓸모 있다.
        lot.sort(key=lambda x: (-len(x['specs']), x.get('reportDate') or ''),
                 reverse=False)
        lot.sort(key=lambda x: -len(x['specs']))
        lot = lot[:CAP_PER_CAT]
        counts[key] = len(lot)
        listed.extend(lot)
    print('목록분 ' + str(len(listed)) + '개를 실었습니다.')

    # 칸별 상태. 앱은 이걸 보고 어떤 칸을 열지 정한다.
    cells = []
    ver_by_cat = {}
    for p in verified:
        c = p.get('cell')
        if c:
            ver_by_cat[c] = ver_by_cat.get(c, 0) + 1
    for g, gl, key, label, _w in CATS:
        nv = ver_by_cat.get(key, 0)
        nl = counts.get(key, 0)
        if nv >= MIN_POOL:
            state = 'ranked'      # 점수와 순위를 낸다
        elif nv + nl >= MIN_POOL:
            state = 'listed'      # 목록만 보여 준다
        else:
            state = 'closed'      # 아직 열지 않는다
        cells.append({'grp': g, 'grpLabel': gl, 'key': key, 'label': label,
                      'verified': nv, 'listed': nl, 'state': state})

    out = {
        'version': TODAY,
        'minPool': MIN_POOL,
        'sources': [
            {'key': 'oliveyoung',
             'name': '올리브영 상품정보 고시(화장품법 제10조)',
             'use': '가격 · 전성분 (사람이 눈으로 확인)'},
            {'key': 'mfds',
             'name': '식품의약품안전처 기능성화장품 보고품목정보',
             'use': 'SPF · PA · 내수성 · pH · 에탄올 · 기능성 인정'},
        ],
        'aiNote': ('제품 이름 정리에 생성형 AI를 썼습니다. '
                   'SPF·PA·pH 같은 숫자는 AI를 거치지 않은 식약처 원본입니다.'),
        'cells': cells,
        'segments': cur.get('segments') or [],
        'products': verified + listed,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False,
                  separators=(',', ':'))

    kb = os.path.getsize(OUT) // 1024
    if kb > WARN_KB:
        print('! 파일이 ' + str(kb) + 'KB 입니다. ' + str(WARN_KB)
              + 'KB를 넘었으니 대분류별로 쪼갤 때가 됐습니다.')

    L = ['# 상품 파일 만든 결과', '',
         '- **실행일**: ' + TODAY,
         '- **확인분**: ' + str(len(verified)) + '개',
         '- **목록분**: ' + str(len(listed)) + '개',
         '- **파일 크기**: ' + str(kb) + 'KB'
         + (' — 700KB를 넘었습니다. 쪼갤 때가 됐습니다.' if kb > WARN_KB else ''),
         '']
    L.append('## 칸별 상태')
    L.append('')
    L.append('| 대분류 | 세부 칸 | 확인분 | 목록분 | 상태 |')
    L.append('|---|---|---|---|---|')
    names = {'ranked': '순위까지', 'listed': '목록만', 'closed': '아직 닫힘'}
    prev = None
    for c in cells:
        L.append('| ' + (c['grpLabel'] if c['grp'] != prev else '') + ' | '
                 + c['label'] + ' | ' + str(c['verified']) + ' | '
                 + str(c['listed']) + ' | ' + names[c['state']] + ' |')
        prev = c['grp']
    L.append('')
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print(OUT + ' 와 ' + REPORT + ' 를 남겼습니다.')


if __name__ == '__main__':
    main()
