import json

PROMPT = """你是 YouTube 頻道「{channel}」的編劇。觀眾:{audience}。語氣:{tone}。
為題目「{topic}」寫一支{length}的旁白。
規則:
1. 第一段是完整句子的開場鉤子,直接點出觀眾的痛點(不要碎句)。
2. 中間每一段結尾都要有一句收束句,說清楚這段的結論。
3. 最後一段收尾並邀請訂閱,留下下一集的懸念。
4. 只能使用下列事實中的數字,且數字必須和它的主體寫在同一句;沒列出的數字一律不要寫:
{facts}
只輸出 JSON,格式:{{"title": "...", "description": "...", "segments": [{{"text": "..."}}]}}"""


def write_script(topic, niche, llm, shorts=False):
    facts = "\n".join("- %s:%s" % (f["subject"], f["value"]) for f in niche.get("facts") or [])
    raw = llm(PROMPT.format(
        channel=niche["channel_name"], audience=niche["audience"], tone=niche["tone"],
        topic=topic,
        length="直式短片(Shorts),全長約 50 秒、3~5 段,每段一兩句" if shorts
        else "約 %s 分鐘的長片" % niche.get("minutes", 8),
        facts=facts or "(無,全文不要出現任何數字)",
    ))
    try:
        s = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError as e:
        raise ValueError("LLM 回傳的不是 JSON:%s" % raw[:200]) from e
    validate(s)
    return s


def validate(s):
    title, desc = str(s.get("title", "")), str(s.get("description", ""))
    segs = s.get("segments") or []
    errs = []
    if not title.strip():
        errs.append("title 空白")
    if len(title) > 100:
        errs.append("title 超過 100 字(%d)" % len(title))
    if len(desc.encode("utf-8")) > 5000:
        errs.append("description 超過 5000 bytes")
    if "<" in title + desc or ">" in title + desc:
        errs.append("title/description 不可含 < >")
    if len(segs) < 3:
        errs.append("segments 至少 3 段(實際 %d)" % len(segs))
    if any(not str(x.get("text", "")).strip() for x in segs):
        errs.append("有空白段落")
    if errs:
        raise ValueError(";".join(errs))
