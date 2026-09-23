"""事實閘門(粗篩,不是事實查核):腳本裡每個阿拉伯數字都必須能在 facts 找到同一個
「數字 + 單位首字 + 負號字元」,且那筆 fact 的主體要出現在同一句;同句出現另一個已知主體
時歸屬有歧義,一樣擋。它只比對字元,不懂語意:漲/跌、衰退/成長、哪個指標、哪一期、多字單位
(兆美元 vs 兆元)一律看不出來。能擋的是「憑空編的數字」和「數字掛錯主體」;其餘要人工看。
PLAYBOOK.md §5 列的是已知例子,不是完整清單。

以下是實際判準(事實和腳本套用同一套規則):

- 正規化:先做 NFKC,全形、上標、下標、圈號數字(１ ¹ ₁ ①)一律轉成一般數字,％ 轉成 %。
- 數字:千分位逗號去掉。逗號只認夾在兩個數字之間的,「12,」後面那個逗號不算數字的一部分。
- 單位:數字後面(可以跳過空白)第一個字元。字串結尾,或這個字元是「的、是、在、和、與、及、
  逗號、頓號」,或是負號/連字號類字元(範圍連接號,例如「10-12.5%」的「-」),單位記為空字串;
  其餘任何字元(含 %、倍、萬、億、元、美、° 等)原樣當單位,必須完全相同才放行。
- 負號:負號/連字號類字元 = Unicode 所有 Pd(各種連字號、破折號)加上數學減號 −。數字前面
  (跳過空白)是這類字元、而它再往前(跳過空白)不是數字,才算負號;前面是數字時是範圍連字號,
  「10-12.5%」「10 - 12.5%」拆成 10 和 12.5,不產生 -12.5。正負號算進數字本身。
- 括號:數字前面(跳過空白)是「(」時,正負不明(會計寫法用括號表示負數),只跟同樣寫括號的
  fact 對得上。
- 斷句:「。!?」、換行,以及不夾在兩個數字之間的半形句點。
- 年份豁免:只認 (19|20)dd 這四碼精確格式、且緊接在後面的字元剛好是「年」,才放行,不查
  真假、也不管有沒有對應 fact。這是刻意留下的已知漏洞,PLAYBOOK.md §5 有列,沒有修。
"""
import re
import unicodedata

NUM = re.compile(r"\d(?:[\d,]*\d)?(?:\.\d+)?")
# 半形句點只有不夾在兩個數字之間時才斷句,否則小數會被切開
SENT = re.compile(r"(?:[^。!?\n.]|(?<=\d)\.(?=\d))+")
YEAR = re.compile(r"(19|20)\d\d$")
UNIT_BLANK = {"的", "是", "在", "和", "與", "及", ",", "，", "、"}


def _normalize(text):
    """NFKC:全形/上標/下標/圈號數字(１、¹、①)轉成一般數字,％→%、⁻→−。
    不先轉的話這些寫法整個看不見 = 靜默放行。"""
    return unicodedata.normalize("NFKC", str(text))


def _is_neg(ch):
    """負號/連字號類字元:Unicode 所有 Pd(各種連字號、破折號)加上數學減號 −。"""
    return ch == "−" or unicodedata.category(ch) == "Pd"


def _unit_after(text, pos):
    """單位 = 數字後面(跳過空白)第一個字元。字串結尾、UNIT_BLANK 裡的虛字/標點,或負號/
    連字號類字元(範圍連接號,例如「10-12.5%」的「-」),單位記為空字串。"""
    i = pos
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n:
        return ""
    ch = text[i]
    if ch in UNIT_BLANK or _is_neg(ch):
        return ""
    return ch


def _normalize_num(raw):
    """去除千分位逗號。正負號不在這裡處理,由 _iter_numbers 依前一個字元判斷後加回來。"""
    return raw.replace(",", "")


def _iter_numbers(text):
    """依序找出 text 裡每個數字,yield (end, normalized)。end 是數字本身(不含負號)的結尾
    位置,用來抓緊接其後的單位;normalized 依情況帶前綴:
    - 往前跳過空白,碰到負號字元、而它再往前(跳過空白)不是數字 → 負號,前綴「-」。
      前面是數字時(「10-12.5」「10 - 12.5」)是範圍連字號,不算負號。
    - 往前跳過空白,碰到「(」→ 前綴「(」。括號可能是會計寫法的負數,正負不明,只跟同樣
      寫括號的 fact 對得上。"""
    for m in NUM.finditer(text):
        start, end = m.start(), m.end()
        num = _normalize_num(m.group())
        i = _skip_space_back(text, start - 1)
        if i >= 0 and _is_neg(text[i]):
            j = _skip_space_back(text, i - 1)
            if j < 0 or not text[j].isdigit():
                num = "-" + num
        elif i >= 0 and text[i] == "(":
            num = "(" + num
        yield end, num


def _skip_space_back(text, i):
    while i >= 0 and text[i].isspace():
        i -= 1
    return i


def _fact_tokens(value):
    """一筆 fact value 裡每個數字連同其單位,回傳 {(number, unit), ...}。"""
    text = _normalize(value)
    return {(num, _unit_after(text, end)) for end, num in _iter_numbers(text)}


def check(script, facts):
    texts = [script.get("title", ""), script.get("description", "")]
    texts += [seg.get("text", "") for seg in script.get("segments", [])]
    problems = []
    for text in texts:
        for sent in SENT.findall(_normalize(text)):
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
                present_owners = {s for s in owner_subjects if s.strip() and s in sent}  # 空主體不算提到
                if not present_owners:
                    who = "、".join(owner_subjects)
                    problems.append("數字 %s%s 屬於 %s,但同一句沒有提到:「%s」" % (n, unit, who, sent))
                    continue
                other_subjects = {str(f["subject"]) for f in facts
                                   if str(f["subject"]).strip() and str(f["subject"]) not in owner_subjects
                                   and str(f["subject"]) in sent}
                if other_subjects:
                    problems.append("數字 %s%s 的歸屬有歧義,同一句還出現 %s:「%s」"
                                     % (n, unit, "、".join(other_subjects), sent))
    # 以下是刻意不處理、發布前要人工看的已知漏洞(例子見 PLAYBOOK.md §5,不是完整清單):
    # 中文數字抓不到、facts 裡沒登記的新主體看不出是另一個主體、主體比對用子字串
    # (「中鋼」對得上「中鋼構」)、分號/逗號不斷句、19xx/20xx 接「年」一律放行、
    # 語意層面(漲/跌、指標、期間、多字單位)完全不查。
    return problems
