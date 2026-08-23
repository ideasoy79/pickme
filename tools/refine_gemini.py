#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
픽미닷 정제기 — 식약처 품목명을 사람이 아는 이름으로 다듬는다.

이 파일은 GitHub Actions 안에서만 돌아간다. 사람이 직접 실행할 일은 없다.
인증키는 코드에 없고 GitHub Secrets(GEMINI_API_KEY)에서 읽는다.

--------------------------------------------------------------------
AI가 하는 일과 하지 않는 일을 여기서 못 박는다.
--------------------------------------------------------------------
AI가 하는 일 (판정과 정리):
  · 품목명에서 브랜드와 제품명을 갈라낸다
  · 소비자가 살 수 있는 제품인지, 공장 벌크·OEM 반제품인지 가른다
  · 품목명만으로 알 수 있는 제형을 정한다 (폼인지 젤인지 등)
  · 헷갈리면 모른다고 답하게 한다

AI가 절대 손대지 않는 것 (사실):
  · SPF, PA, 내수성, pH, 에탄올 초과 여부, 미백·주름·자외선 인정
  · 보고일, 업체명, 제조국
  이 값들은 식약처 원본에서 그대로 복사한다. AI 응답에 같은 이름의
  칸이 들어 있어도 무시한다. 사실을 지어낼 자리를 아예 만들지 않는다.

이것이 픽미닷 두 번째 기준("사실을 주장하면 출처와 확인 날짜를 적는다")을
AI를 쓰면서도 지키는 방법이다.
--------------------------------------------------------------------

무료 한도 안에서 돌리기 위한 장치:
  · 한 번에 여러 건을 묶어 보낸다 (BATCH)
  · 호출 사이에 쉰다 (SLEEP)
  · 429가 오면 기다렸다 다시 건다
  · 끝낸 것은 그때그때 파일에 적는다. 중간에 멈춰도 다시 돌리면 이어서 한다.
  · 하루 상한(MAX_CALLS)에 닿으면 곱게 멈춘다. 내일 또 돌리면 된다.
"""

import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_mfds import CATS, pick_cat  # noqa: E402

KEY = os.environ.get('GEMINI_API_KEY', '').strip()
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash').strip()
BATCH = int(os.environ.get('BATCH', '25') or '25')
SLEEP = float(os.environ.get('SLEEP', '4') or '4')
PER_CAT = int(os.environ.get('PER_CAT', '60') or '60')
PER_ENTP = int(os.environ.get('PER_ENTP', '3') or '3')
MAX_CALLS = int(os.environ.get('MAX_CALLS', '120') or '120')
DRY = os.environ.get('DRY_RUN', '').strip() == '1'

IN_JSON = os.path.join('data', 'mfds.json')
OUT_JSON = os.path.join('data', 'refined.json')
OUT_REPORT = os.path.join('data', 'refine_report.md')

TODAY = datetime.date.today().isoformat()

ENDPOINT = ('https://generativelanguage.googleapis.com/v1beta/models/'
            + MODEL + ':generateContent')

# 세부 칸 키 -> 이름. AI에게 "이 중에서만 고르라"고 줄 목록을 만들 때 쓴다.
CAT_LABEL = {}
GRP_CATS = {}
for _g, _gl, _k, _l, _w in CATS:
    CAT_LABEL[_k] = _l
    GRP_CATS.setdefault(_g, []).append((_k, _l))


PROMPT_HEAD = """당신은 한국 화장품 매장의 상품 담당자입니다.
식품의약품안전처에 보고된 '품목명'을 받아서, 실제로 소비자가 알아볼 수 있는
형태로 정리하는 일을 합니다.

주의: 아래 목록의 품목명 외에는 아무것도 참고하지 마세요.
당신이 알고 있다고 생각하는 가격, 성분, 후기, 평판은 절대 쓰지 마세요.
품목명 글자에서 읽어낼 수 있는 것만 답하세요.

각 항목마다 다음을 판단하세요.

1) retail: 이 제품을 일반 소비자가 매장이나 온라인에서 살 수 있을 것 같은가?
   - "OEM", "벌크", "반제품", "샘플", "판촉", "증정", "테스터", "리필용",
     "업소용", 숫자·코드만 나열된 이름, 수출 전용으로 보이는 영문 코드명 등은 false
   - 브랜드명과 제품명이 뚜렷하게 보이면 true
   - 애매하면 false. 확실할 때만 true로 하세요.

2) brand: 품목명 앞부분의 브랜드. 품목명에 브랜드가 안 보이면 빈 문자열.
   회사 이름을 당신이 추측해서 넣지 마세요.

3) title: 브랜드를 뺀 제품 이름. 규격(용량, 호수)이나 보고용 접미사는 덜어냅니다.

4) cat: 아래 목록의 키 중 하나. 품목명으로 제형을 알 수 없으면 "" (빈 문자열).
   특히 그냥 "클렌저"라고만 되어 있으면 폼인지 젤인지 알 수 없으므로 ""입니다.

5) note: 품목명에서 읽히는 특징을 한 줄로. 없으면 빈 문자열.
   예: "무기자차 표기", "톤업 기능 표기", "저자극 표기"
   품목명에 안 적힌 것은 쓰지 마세요.

고를 수 있는 cat 값:
"""

PROMPT_TAIL = """
답은 JSON 배열 하나로만 주세요. 설명 문장을 덧붙이지 마세요.
배열의 길이와 순서는 입력과 정확히 같아야 합니다.
형식: [{"i":0,"retail":true,"brand":"","title":"","cat":"","note":""}, ...]

입력:
"""


def die(msg):
    print('')
    print('=' * 60)
    print(msg)
    print('=' * 60)
    sys.exit(1)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print('! ' + path + ' 읽기 실패: ' + str(e))
        return default


def save_json(path, obj):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def cat_menu(grp):
    """이 대분류 안의 세부 칸만 보여 준다.
    선케어를 고르는 자리에서 크림 칸 목록까지 보여 줄 이유가 없다."""
    out = []
    for k, l in GRP_CATS.get(grp, []):
        out.append('  ' + k + ' = ' + l)
    return '\n'.join(out)


def call_gemini(prompt):
    """제미나이를 한 번 부른다. 429·5xx는 기다렸다 다시 건다."""
    body = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0,
            'responseMimeType': 'application/json',
            'maxOutputTokens': 8192,
        },
    }
    data = json.dumps(body).encode('utf-8')
    wait = 20
    for attempt in range(5):
        req = urllib.request.Request(
            ENDPOINT,
            data=data,
            headers={'Content-Type': 'application/json',
                     'x-goog-api-key': KEY},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                out = json.loads(res.read().decode('utf-8'))
            cands = out.get('candidates') or []
            if not cands:
                return None, '응답에 candidates 없음'
            parts = (cands[0].get('content') or {}).get('parts') or []
            text = ''
            for p in parts:
                text += p.get('text') or ''
            if not text.strip():
                return None, '응답이 비어 있음'
            return text, ''
        except urllib.error.HTTPError as e:
            code = e.code
            detail = ''
            try:
                detail = e.read().decode('utf-8')[:200]
            except Exception:
                pass
            if code == 429:
                print('    · 한도에 걸렸습니다. ' + str(wait) + '초 쉽니다.')
                time.sleep(wait)
                wait = min(wait * 2, 300)
                continue
            if code >= 500:
                print('    · 서버 오류 ' + str(code) + '. 10초 쉽니다.')
                time.sleep(10)
                continue
            return None, 'HTTP ' + str(code) + ' ' + detail
        except Exception as e:
            print('    · 통신 오류: ' + str(e) + '. 10초 쉽니다.')
            time.sleep(10)
    return None, '여러 번 시도했지만 실패'


def parse_reply(text, n):
    """AI 답을 배열로 만든다. 못 읽으면 None."""
    t = (text or '').strip()
    if t.startswith('```'):
        nl = t.find('\n')
        if nl > -1:
            t = t[nl + 1:]
        if t.rstrip().endswith('```'):
            t = t.rstrip()[:-3]
    lb = t.find('[')
    rb = t.rfind(']')
    if lb < 0 or rb < lb:
        return None
    try:
        arr = json.loads(t[lb:rb + 1])
    except Exception:
        return None
    if not isinstance(arr, list):
        return None
    # 길이가 안 맞으면 통째로 버린다. 순서가 어긋난 채로 붙이면
    # 엉뚱한 제품에 엉뚱한 이름이 붙는다. 그게 제일 나쁘다.
    if len(arr) != n:
        return None
    return arr


def clean_str(v, limit):
    s = str(v or '').strip()
    if len(s) > limit:
        s = s[:limit]
    return s


def pick_candidates(rows, done_ids):
    """칸마다 후보를 골라 온다.

    최근에 보고된 것을 먼저 본다. 다만 한 업체가 한 칸을 통째로
    가져가면 화면이 그 회사 카탈로그가 되어 버리므로 업체당 상한을 둔다.
    """
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r.get('cat') or '', []).append(r)

    picked = []
    stat = {}
    for _g, _gl, key, _l, _w in CATS:
        lot = by_cat.get(key) or []
        lot.sort(key=lambda r: r.get('reportDate') or '', reverse=True)
        per = {}
        got = []
        for r in lot:
            if len(got) >= PER_CAT:
                break
            e = r.get('entp') or ''
            if per.get(e, 0) >= PER_ENTP:
                continue
            per[e] = per.get(e, 0) + 1
            got.append(r)
        stat[key] = {'pool': len(lot), 'picked': len(got)}
        for r in got:
            if r.get('id') not in done_ids:
                picked.append(r)
    return picked, stat


def main():
    if not DRY and not KEY:
        die('GEMINI_API_KEY 가 없습니다.\n'
            '저장소 Settings → Secrets and variables → Actions 에서\n'
            'GEMINI_API_KEY 라는 이름으로 넣어 주세요.')

    src = load_json(IN_JSON, None)
    if not src:
        die(IN_JSON + ' 이 없습니다. 수집을 먼저 돌려 주세요.')
    rows = src.get('items') if isinstance(src, dict) else src
    if not rows:
        die(IN_JSON + ' 안에 항목이 없습니다.')
    print('수집분 ' + str(len(rows)) + '건을 읽었습니다.')

    prev = load_json(OUT_JSON, {})
    done = prev.get('items') or {}
    print('이미 정제한 것 ' + str(len(done)) + '건은 건너뜁니다.')

    todo, stat = pick_candidates(rows, done)
    print('이번에 볼 것 ' + str(len(todo)) + '건.')

    by_id = {}
    for r in rows:
        by_id[r.get('id')] = r

    calls = 0
    ok = 0
    bad = 0
    i = 0
    stopped = ''
    while i < len(todo):
        if calls >= MAX_CALLS:
            stopped = '하루 호출 상한(' + str(MAX_CALLS) + '번)에 닿아 멈췄습니다.'
            print(stopped + ' 남은 것은 다음 실행에서 이어서 합니다.')
            break

        chunk = todo[i:i + BATCH]
        i += BATCH
        grp = chunk[0].get('grp') or ''

        lines = []
        for n in range(len(chunk)):
            lines.append(str(n) + '. ' + (chunk[n].get('name') or ''))
        prompt = (PROMPT_HEAD + cat_menu(grp) + PROMPT_TAIL
                  + '\n'.join(lines))

        if DRY:
            print('  [연습] ' + str(len(chunk)) + '건 · ' + grp
                  + ' · 글자수 ' + str(len(prompt)))
            calls += 1
            continue

        calls += 1
        print('  ' + str(calls) + '번째 요청 · ' + grp + ' · '
              + str(len(chunk)) + '건')
        text, err = call_gemini(prompt)
        if not text:
            print('    ! 실패: ' + err)
            bad += len(chunk)
            time.sleep(SLEEP)
            continue

        arr = parse_reply(text, len(chunk))
        if arr is None:
            print('    ! 답을 읽지 못했습니다. 이 묶음은 건너뜁니다.')
            bad += len(chunk)
            time.sleep(SLEEP)
            continue

        for n in range(len(chunk)):
            r = chunk[n]
            a = arr[n] if isinstance(arr[n], dict) else {}
            cat = clean_str(a.get('cat'), 24)
            # AI가 이 대분류 밖의 칸을 말했으면 안 믿는다.
            valid = [k for k, _l in GRP_CATS.get(grp, [])]
            if cat not in valid:
                cat = ''
            done[r.get('id')] = {
                'retail': bool(a.get('retail')),
                'brand': clean_str(a.get('brand'), 40),
                'title': clean_str(a.get('title'), 90),
                'cat': cat,
                'note': clean_str(a.get('note'), 60),
                'by': MODEL,
                'at': TODAY,
            }
            ok += 1

        # 그때그때 적어 둔다. 중간에 멈춰도 여기까지는 남는다.
        save_json(OUT_JSON, {'version': TODAY, 'model': MODEL,
                             'items': done})
        time.sleep(SLEEP)

    save_json(OUT_JSON, {'version': TODAY, 'model': MODEL, 'items': done})
    write_report(rows, by_id, done, stat, calls, ok, bad, stopped)
    print('')
    print('정제 ' + str(ok) + '건 성공, ' + str(bad) + '건 실패. '
          + '누적 ' + str(len(done)) + '건.')
    print(OUT_JSON + ' 와 ' + OUT_REPORT + ' 를 남겼습니다.')


def write_report(rows, by_id, done, stat, calls, ok, bad, stopped):
    L = []
    L.append('# 정제 결과 요약')
    L.append('')
    L.append('- **실행일**: ' + TODAY)
    L.append('- **모델**: ' + MODEL)
    L.append('- **이번 요청 수**: ' + str(calls) + '번')
    L.append('- **이번에 정제**: ' + str(ok) + '건 (실패 ' + str(bad) + '건)')
    L.append('- **누적 정제**: ' + str(len(done)) + '건')
    if stopped:
        L.append('- **멈춘 이유**: ' + stopped)
    L.append('')
    L.append('AI는 이름 정리와 판정만 했습니다. SPF·PA·pH·에탄올·미백/주름 인정은')
    L.append('식약처 원본 값을 그대로 씁니다. AI가 손대지 않았습니다.')
    L.append('')

    # 칸별로 "팔 수 있는 것"이 몇 개 남았는지가 핵심 숫자다.
    retail_by_cat = {}
    unknown_by_cat = {}
    for pid, v in done.items():
        r = by_id.get(pid)
        if not r:
            continue
        c = v.get('cat') or r.get('cat')
        if v.get('retail'):
            retail_by_cat[c] = retail_by_cat.get(c, 0) + 1
        if not v.get('cat'):
            unknown_by_cat[r.get('cat')] = unknown_by_cat.get(r.get('cat'), 0) + 1

    L.append('## 칸별 현황')
    L.append('')
    L.append('| 대분류 | 세부 칸 | 수집분 | 후보로 뽑음 | 소비자용 판정 |')
    L.append('|---|---|---|---|---|')
    prev_g = None
    for g, gl, key, label, _w in CATS:
        s = stat.get(key) or {'pool': 0, 'picked': 0}
        L.append('| ' + (gl if g != prev_g else '') + ' | ' + label + ' | '
                 + str(s['pool']) + ' | ' + str(s['picked']) + ' | '
                 + str(retail_by_cat.get(key, 0)) + ' |')
        prev_g = g
    L.append('')

    L.append('## 정제 결과 미리보기')
    L.append('')
    L.append('칸마다 최대 5개까지 보여 줍니다. 이름이 이상하면 알려 주세요.')
    L.append('')
    shown = {}
    for pid, v in done.items():
        r = by_id.get(pid)
        if not r or not v.get('retail'):
            continue
        c = v.get('cat') or r.get('cat')
        shown.setdefault(c, []).append((r, v))
    for g, gl, key, label, _w in CATS:
        lot = shown.get(key) or []
        if not lot:
            continue
        L.append('**' + gl + ' › ' + label + '** (' + str(len(lot)) + '건)')
        L.append('')
        for r, v in lot[:5]:
            bits = []
            if r.get('spf'):
                bits.append('SPF' + r['spf'])
            if r.get('pa'):
                bits.append(r['pa'])
            if r.get('waterproof'):
                bits.append(r['waterproof'])
            if r.get('ph'):
                bits.append('pH ' + r['ph'])
            if r.get('ethanolOver'):
                bits.append('에탄올 4% 초과')
            if r.get('effects'):
                bits.append('/'.join(r['effects']))
            if v.get('note'):
                bits.append(v['note'])
            tail = (' — ' + ', '.join(bits)) if bits else ''
            nm = ((v.get('brand') + ' ') if v.get('brand') else '') + (v.get('title') or r.get('name'))
            L.append('- ' + nm + tail)
        L.append('')

    if unknown_by_cat:
        L.append('## 제형을 정하지 못한 것')
        L.append('')
        L.append('AI가 품목명만으로는 알 수 없다고 답한 것들입니다.')
        L.append('모르는 것을 안다고 적지 않기 위해 따로 둡니다.')
        L.append('')
        for k, n in sorted(unknown_by_cat.items(), key=lambda x: -x[1]):
            L.append('- ' + CAT_LABEL.get(k, k) + ': ' + str(n) + '건')
        L.append('')

    d = os.path.dirname(OUT_REPORT)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
