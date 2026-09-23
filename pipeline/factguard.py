"""事實閘門:腳本裡每個阿拉伯數字都必須來自 facts,且那筆 fact 的主體要出現在同一句。
只查「數字存在」不夠 —— 真實數字掛到別人頭上照樣是編造,單位不同也是編造(12.5% 不能拿來
背書 12.5 倍)。同句出現另一個已知主體時歸屬有歧義,一樣擋。無法判定一律擋(fail-closed)。"""
import re

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENT = re.compile(r"[^。！？!?\n]+")
YEAR = re.compile(r"(19|20)\d\d$")
UNIT_CHARS = {"%": "%", "％": "%", "倍": "倍", "萬": "萬", "億": "億", "元": "元"}


def _unit_after(text, pos):
    """緊接在數字後面的單位,正規化(％ 視同 %);沒有單位回傳空字串。"""
    return UNIT_CHARS.get(text[pos:pos + 1], "")


def _fact_tokens(value):
    """一筆 fact value 裡每個數字連同其單位,回傳 {(number, unit), ...}。"""
    text = str(value)
    return {(m.group().replace(",", ""), _unit_after(text, m.end())) for m in NUM.finditer(text)}


def check(script, facts):
    texts = [script.get("title", ""), script.get("description", "")]
    texts += [seg.get("text", "") for seg in script.get("segments", [])]
    problems = []
    for text in texts:
        for sent in SENT.findall(text):
            for m in NUM.finditer(sent):
                n = m.group().replace(",", "")
                if YEAR.match(n) and sent[m.end():m.end() + 1] == "年":
                    continue  # 年份(限 19xx/20xx 接「年」,3000 這種不算)
                unit = _unit_after(sent, m.end())
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
    # ponytail: 只抓阿拉伯數字;「三成」「十二億」這類中文數字抓不到
    # ponytail: 主體排除只認得出現在 facts 清單裡的主體;句中出現的是沒登記在 facts 的新主體
    #           (例如「乙」不在 facts 裡)時,看不出那是另一個主體,擋不到 —— 這兩類都要靠人工看
    return problems
