from pipeline.factguard import check

FACTS = [{"subject": "甲公司", "value": "12.5%"}]

def S(*texts):
    return {"title": "t", "description": "d", "segments": [{"text": t} for t in texts]}

def test_owned_number_passes():
    assert check(S("甲公司毛利率是12.5%。"), FACTS) == []

def test_unknown_number_blocked():
    assert check(S("甲公司毛利率是30%。"), FACTS)

def test_number_on_wrong_subject_blocked():
    # 已知陽性:數字存在於 facts,但屬於甲不屬於乙
    assert check(S("乙公司毛利率是12.5%。"), FACTS)

def test_title_is_checked():
    s = S("沒有數字。")
    s["title"] = "暴漲99%"
    assert check(s, FACTS)

def test_year_allowed():
    assert check(S("2024年甲公司表現如何?"), FACTS) == []

def test_no_facts_any_number_blocked():
    assert check(S("有7成的人會錯。"), [])
