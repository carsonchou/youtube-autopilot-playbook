PROMPT = """你是 YouTube 頻道「{channel}」的選題編輯。觀眾:{audience}。
參考這些種子主題:{seeds}
提出一個觀眾會「主動搜尋」的影片題目(像搜尋框裡會打的問題),不要和這些已做過的重複:{used}
{performance}只輸出題目本身,一行。"""


def _performance_block(performance):
    """把過去表現(依觀看分鐘)整理成一段 prompt 文字;沒有 performance 就不加。"""
    if not performance:
        return ""
    best = performance[:5]
    lines = ["過去表現最好的題目(依觀看分鐘):" + "、".join(p["topic"] for p in best)]
    worst = performance[5:][-5:]
    if worst:
        lines.append("過去表現最差的題目(依觀看分鐘):" + "、".join(p["topic"] for p in worst))
    return "\n".join(lines) + "\n"


def pick_topic(niche, used, llm, performance=None):
    raw = llm(PROMPT.format(
        channel=niche["channel_name"],
        audience=niche["audience"],
        seeds="、".join(niche.get("seed_topics", [])),
        used="、".join(used[-50:]) or "(無)",
        performance=_performance_block(performance),
    ))
    lines = raw.strip().splitlines()
    topic = lines[0].strip().strip("「」\"'") if lines else ""
    if not topic:
        raise ValueError("LLM 沒有給題目")
    if topic in used:
        raise ValueError("題目重複:" + topic)
    return topic
