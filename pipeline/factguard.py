"""事實閘門:腳本裡每個阿拉伯數字都必須來自 facts,且那筆 fact 的主體要出現在同一句。
只查「數字存在」不夠 —— 真實數字掛到別人頭上照樣是編造。無法判定一律擋(fail-closed)。"""
import re

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENT = re.compile(r"[^。！？!?\n]+")


def _nums(text):
    return {m.group().replace(",", "") for m in NUM.finditer(str(text))}


def check(script, facts):
    texts = [script.get("title", ""), script.get("description", "")]
    texts += [seg.get("text", "") for seg in script.get("segments", [])]
    problems = []
    for text in texts:
        for sent in SENT.findall(text):
            for m in NUM.finditer(sent):
                n = m.group().replace(",", "")
                if len(n) == 4 and sent[m.end():m.end() + 1] == "年":
                    continue  # 年份
                owners = [f for f in facts if n in _nums(f.get("value", ""))]
                if not owners:
                    problems.append("數字 %s 不在 facts:「%s」" % (n, sent))
                elif not any(str(f["subject"]) in sent for f in owners):
                    who = "、".join(str(f["subject"]) for f in owners)
                    problems.append("數字 %s 屬於 %s,但同一句沒有提到:「%s」" % (n, who, sent))
    # ponytail: 只抓阿拉伯數字;「三成」「十二億」這類中文數字抓不到,要擋就加中文數字解析
    return problems
