PROMPT = """你是 YouTube 頻道「{channel}」的選題編輯。觀眾:{audience}。
參考這些種子主題:{seeds}
提出一個觀眾會「主動搜尋」的影片題目(像搜尋框裡會打的問題),不要和這些已做過的重複:{used}
只輸出題目本身,一行。"""


def pick_topic(niche, used, llm):
    raw = llm(PROMPT.format(
        channel=niche["channel_name"],
        audience=niche["audience"],
        seeds="、".join(niche.get("seed_topics", [])),
        used="、".join(used[-50:]) or "(無)",
    ))
    lines = raw.strip().splitlines()
    topic = lines[0].strip().strip("「」\"'") if lines else ""
    if not topic:
        raise ValueError("LLM 沒有給題目")
    if topic in used:
        raise ValueError("題目重複:" + topic)
    return topic
