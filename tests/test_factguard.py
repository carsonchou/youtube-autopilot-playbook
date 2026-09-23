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

def test_fake_year_not_exempted():
    # A1:年份豁免只限 (19|20)dd 後接「年」,3000 不是真的年份格式
    assert check(S("3000年都不會虧。"), FACTS)

def test_same_number_different_unit_blocked():
    # A2:數字相同但單位不同要擋(12.5% 的事實不能拿來背書 12.5 倍)
    assert check(S("甲公司股價漲了12.5倍。"), FACTS)

def test_same_number_same_unit_passes():
    assert check(S("甲公司毛利率12.5%。"), FACTS) == []

FACTS_TWO = [{"subject": "甲", "value": "12.5%"}, {"subject": "丙", "value": "30%"}]

def test_ambiguous_subject_blocked():
    # A3:句中同時出現另一個「不擁有此數字」的已知 fact 主體,歸屬有歧義,要擋
    assert check(S("丙公司比甲公司的12.5%高。"), FACTS_TWO)
