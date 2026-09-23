"""事實閘門:腳本裡每個阿拉伯數字都必須來自 facts,且那筆 fact 的主體要出現在同一句。
只查「數字存在」不夠 —— 真實數字掛到別人頭上照樣是編造,單位不同也是編造(12.5% 不能拿來
背書 12.5 倍)。同句出現另一個已知主體時歸屬有歧義,一樣擋。

以下是實際判準(完整已知擋不到/會誤判清單見 PLAYBOOK.md §5):

- 單位:數字後面(可以跳過空白)第一個字元。字串結尾、空白,或這個字元是
  「的、是、在、和、與、及、，、、」這幾個虛字/標點,或是 -、−、－、﹣、–、— 這幾個
  連字號/負號字元(用來連接範圍,例如「10-12.5%」的「-」),單位記為空字串;其餘任何字元
  (含 %、倍、萬、億、元、美、° 等)原樣當單位。％ 正規化成 %。事實和腳本用同一套規則取
  單位,必須完全相同才放行 —— 不再有內建的單位白名單。
- 負號:字元屬於 -、−、－、﹣、–、— 之一,且緊接在數字前面、而它再前面那個字元不是數字,
  才算負號(數字前接數字時是範圍連字號,例如「10-12.5%」要拆成 10 和 12.5,不產生 -12.5)。
  事實和腳本都套用同一套規則,正負號算進數字本身,不同號視為不同數字。
- 年份豁免:只認 (19|20)dd 這四碼精確格式、且緊接在後面的字元剛好是「年」,才放行,不查
  真假、也不管有沒有對應 fact。這是刻意留下的已知漏洞,PLAYBOOK.md §5 有列,沒有修。
"""
import re

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENT = re.compile(r"[^。!?！？\n]+")
YEAR = re.compile(r"(19|20)\d\d$")
NEG_CHARS = set("-−－﹣–—")
UNIT_BLANK = {"的", "是", "在", "和", "與", "及", "，", "、"}


def _unit_after(text, pos):
    """單位 = 數字後面(跳過空白)第一個字元;％正規化成 %。
    字串結尾、空白,「的、是、在、和、與、及、，、、」這幾個虛字/標點,或是 NEG_CHARS
    裡的連字號/負號字元(範圍連接號,例如「10-12.5%」的「-」),單位記為空字串。"""
    i = pos
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n:
        return ""
    ch = text[i]
    if ch in UNIT_BLANK or ch in NEG_CHARS:
        return ""
    if ch == "％":
        return "%"
    return ch


def _normalize_num(raw):
    """去除千分位逗號。正負號不在這裡處理,由 _iter_numbers 依前一個字元判斷後加回來。"""
    return raw.replace(",", "")


def _iter_numbers(text):
    """依序找出 text 裡每個數字,yield (end, normalized)。end 是數字本身(不含負號)的結尾
    位置,用來抓緊接其後的單位;normalized 依情況帶負號前綴。
    負號判定:數字前一個字元屬於 NEG_CHARS,且再前一個字元不是數字,才算負號 —— 數字前接
    數字時(例如「10-12.5」的那個「-」)視為範圍連字號,不算負號,兩邊各自是獨立的數字。"""
    for m in NUM.finditer(text):
        start, end = m.start(), m.end()
        num = _normalize_num(m.group())
        if start > 0 and text[start - 1] in NEG_CHARS:
            if start < 2 or not text[start - 2].isdigit():
                num = "-" + num
        yield end, num


def _fact_tokens(value):
    """一筆 fact value 裡每個數字連同其單位,回傳 {(number, unit), ...}。"""
    text = str(value)
    return {(num, _unit_after(text, end)) for end, num in _iter_numbers(text)}


def check(script, facts):
    texts = [script.get("title", ""), script.get("description", "")]
    texts += [seg.get("text", "") for seg in script.get("segments", [])]
    problems = []
    for text in texts:
        for sent in SENT.findall(text):
            for end, n in _iter_numbers(sent):
                if YEAR.match(n) and sent[end:end + 1] == "年":
                    continue  # 年份豁免,見上方 docstring
                unit = _unit_after(sent, end)
                token = (n, unit)
                owners = [f for f in facts if token in _fact_tokens(f.get("value", ""))]
                if not owners:
                    problems.append("數字 %s%s 不在 facts:「%s」" % (n, unit, sent))
                    continue
                owner_subjects = {str(f["subject"]) for f in owners}
                present_owners = {s for s in owner_subjects if s in sent}
                if not present_owners:
                    who = "、".join(owner_subjects)
                    problems.append("數字 %s%s 屬於 %s,但同一句沒有提到:「%s」" % (n, unit, who, sent))
                    continue
                other_subjects = {str(f["subject"]) for f in facts
                                   if str(f["subject"]) not in owner_subjects and str(f["subject"]) in sent}
                if other_subjects:
                    problems.append("數字 %s%s 的歸屬有歧義,同一句還出現 %s:「%s」"
                                     % (n, unit, "、".join(other_subjects), sent))
    # 以下是刻意不處理、發布前要人工看的已知漏洞,完整清單見 PLAYBOOK.md §5:
    # 中文數字抓不到、facts 裡沒登記的新主體看不出是另一個主體、主體比對用子字串
    # (「中鋼」對得上「中鋼構」)、斷句只認「。!?！?」和換行、19xx/20xx 接「年」一律放行。
    return problems
