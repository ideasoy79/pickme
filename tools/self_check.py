#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# refine_gemini.py 의 위험한 부분만 콕 집어 확인한다.
#
# 여기서 보는 것은 하나다.
# "AI 가 엉뚱하게 답했을 때 그 답이 제품에 붙어버리는가."
# 순서가 어긋난 채로 붙으면 A 제품에 B 이름이 달린다.
# 화면에는 아무 문제 없어 보이므로 아무도 못 잡는다. 그래서 여기서 잡는다.

import io, json, os, sys

os.environ['GEMINI_API_KEY'] = 'TEST'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import refine_gemini as R

ok_n = 0
bad_n = 0


def ck(name, cond, extra=''):
    global ok_n, bad_n
    if cond:
        ok_n += 1
        print('  ok   ' + name)
    else:
        bad_n += 1
        print('  FAIL ' + name + (('  → ' + str(extra)) if extra else ''))


good = ('[{"i":0,"retail":true,"brand":"라네즈","title":"워터뱅크 크림",'
        '"cat":"cr_cream","note":""},'
        '{"i":1,"retail":false,"brand":"","title":"","cat":"","note":""}]')

print('\n== 1. 정상 응답 ==')
a = R.parse_reply(good, 2)
ck('2개 요청에 2개 응답이면 받는다', a is not None and len(a) == 2)
ck('브랜드가 들어온다', a and a[0]['brand'] == '라네즈')

print('\n== 2. 길이가 어긋나면 통째로 버린다 ==')
ck('3개 요청에 2개 응답 → 버림', R.parse_reply(good, 3) is None)
ck('1개 요청에 2개 응답 → 버림', R.parse_reply(good, 1) is None)

print('\n== 3. 껍데기가 붙어 와도 벗겨 낸다 ==')
fenced = '```json\n' + good + '\n```'
ck('```json 울타리를 벗긴다', R.parse_reply(fenced, 2) is not None)
chatty = '네, 알겠습니다.\n' + good + '\n이상입니다.'
ck('앞뒤 잡담을 잘라 낸다', R.parse_reply(chatty, 2) is not None)

print('\n== 4. 망가진 응답 ==')
ck('빈 문자열 → 버림', R.parse_reply('', 2) is None)
ck('JSON 이 아님 → 버림', R.parse_reply('죄송합니다 답할 수 없습니다', 2) is None)
ck('대괄호가 안 닫힘 → 버림', R.parse_reply('[{"i":0}', 2) is None)
ck('배열이 아니고 객체 → 버림', R.parse_reply('{"i":0}', 1) is None)

print('\n== 5. 없는 칸 이름은 지운다 ==')
valid = [k for k, _l in R.GRP_CATS.get('cream', [])]
ck('cream 무리에 진짜 칸이 있다', len(valid) > 0, valid)
ck('cr_cream 은 통과', 'cr_cream' in valid)
ck('AI 가 지어낸 칸은 목록에 없다', 'cr_지어냄' not in valid)

print('\n== 6. 후보 고르기 ==')
rows = []
for i in range(40):
    rows.append({
        'id': 'p' + str(i),
        'name': '시험 제품 ' + str(i),
        'entp': '가짜회사' + str(i % 3),   # 회사 3곳에 몰아 넣는다
        'cat': 'cr_cream',
        'grp': 'cream',
        'reportDate': '2024-01-' + str((i % 28) + 1).zfill(2),
    })
R.PER_ENTP = 3
R.PER_CAT = 60
picked, stat = R.pick_candidates(rows, set())
per = {}
for r in picked:
    per[r['entp']] = per.get(r['entp'], 0) + 1
ck('한 회사가 칸을 독차지하지 못한다 (회사당 최대 ' + str(max(per.values())) + ')',
   max(per.values()) <= 3, per)
ck('여러 회사가 섞인다 (' + str(len(per)) + '곳)', len(per) >= 2)

done = set(['p0', 'p1', 'p2'])
picked2, _s2 = R.pick_candidates(rows, done)
ck('이미 끝낸 것은 두 번 부르지 않는다',
   all(r['id'] not in done for r in picked2))
ck('칸별 셈이 같이 온다', 'cr_cream' in stat and stat['cr_cream']['pool'] == 40, stat.get('cr_cream'))
ck('PER_CAT 위로는 아예 안 본다 (' + str(stat['cr_cream']['picked']) + '개)',
   stat['cr_cream']['picked'] <= 60)

print('\n== 7. 열쇠가 새어나가지 않는다 ==')
src = io.open(os.path.join(HERE, 'refine_gemini.py'),
              encoding='utf-8').read()
ck('소스에 실제 키 문자열이 없다', 'AIza' not in src)
ck('키는 환경변수에서만 읽는다', "environ" in src and 'GEMINI_API_KEY' in src)

print('\n' + ('전부 통과' if bad_n == 0 else str(bad_n) + '개 실패')
      + ' · 통과 ' + str(ok_n) + ' · 실패 ' + str(bad_n))
sys.exit(0 if bad_n == 0 else 1)
