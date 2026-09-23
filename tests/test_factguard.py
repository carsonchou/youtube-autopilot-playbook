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

FACTS_NEG = [{"subject": "乙公司", "value": "-12.5%"}]

def test_negative_sign_ignored_blocked():
    # 正負號要算進數字本身:facts 是 12.5%(正),不能拿來背書 -12.5%
    assert check(S("甲公司毛利率是-12.5%。"), FACTS)

def test_negative_sign_matched_passes():
    # facts 本身是負的,腳本寫同號的負數才放行
    assert check(S("乙公司毛利率是-12.5%。"), FACTS_NEG) == []

def test_negative_fact_does_not_cover_positive_script():
    # facts 是 -12.5%,腳本寫成正的 12.5% 一樣要擋(正負號不同視為不同數字)
    assert check(S("乙公司毛利率是12.5%。"), FACTS_NEG)


# ---- A1:單位定義 ----

def test_fullwidth_percent_normalizes_to_halfwidth():
    facts = [{"subject": "甲", "value": "12.5％"}]  # fact 用全形％
    assert check(S("甲的成長率是12.5%。"), facts) == []  # 腳本用半形%


def test_unit_blank_before_function_word():
    # 數字後緊接虛字「的」,單位記為空;fact 是裸數字(無單位,字串結尾也是空),兩邊都空才放行
    facts = [{"subject": "甲", "value": "12.5"}]
    assert check(S("甲的表現是12.5的顯著成長。"), facts) == []


def test_unit_blank_before_comma():
    facts = [{"subject": "甲", "value": "12.5"}]
    assert check(S("甲的成長是12.5，值得注意。"), facts) == []


def test_unit_literal_char_no_whitelist_matches():
    # 拿掉 6 種單位白名單後,任何字元都可以當單位,不限於 %/倍/萬/億/元
    facts = [{"subject": "甲", "value": "100美元"}]
    assert check(S("甲去年營收100美元。"), facts) == []


def test_unit_literal_char_mismatch_blocked():
    # 同上一筆 fact,但腳本換成「元」不是「美」,單位不同要擋
    facts = [{"subject": "甲", "value": "100美元"}]
    assert check(S("甲去年營收100元。"), facts)


def test_unit_skips_blank_before_symbol():
    facts = [{"subject": "甲", "value": "30%"}]
    assert check(S("甲的獲利成長 30 %。"), facts) == []


# ---- A2:負號與範圍連字號 ----

def test_range_hyphen_not_negative():
    # 「10-12.5%」要拆成 10(無單位)和 12.5%,不能產生 -12.5
    facts = [{"subject": "甲", "value": "10"}, {"subject": "甲", "value": "12.5%"}]
    assert check(S("甲的成長率是10-12.5%。"), facts) == []


def test_fact_range_does_not_produce_negative_token():
    # fact「10-12.5%」不會產生 -12.5,所以腳本裡真正的負數 -12.5% 找不到出處,要擋
    facts = [{"subject": "甲公司", "value": "10-12.5%"}]
    assert check(S("甲公司毛利率是-12.5%。"), facts)


def test_fullwidth_minus_treated_as_negative_blocked():
    # fact 是正的 12.5%,腳本用全形負號寫成 -12.5%,要擋
    assert check(S("甲公司毛利率是－12.5%。"), FACTS)


# ---- 年份豁免:回歸測試,擋不住下面兩種弱化就會失敗 ----

def test_year_exemption_requires_year_suffix_mutation_guard():
    # 若把「後面必須接『年』」的條件拿掉,下面兩句會被誤放行
    assert check(S("預估2024萬元進帳。"), [])
    assert check(S("本次數據來自2024。"), [])


def test_year_exemption_uses_match_not_search_mutation_guard():
    # 若把 YEAR.match 換成 YEAR.search,"12024" 會被誤判成含有 2024 這個年份而放行
    assert check(S("12024年之後淨利有機會翻倍。"), [])


def test_fullwidth_digits_are_checked():
    facts = [{"subject": "甲公司", "value": "毛利率12.5%"}]
    assert check({"segments": [{"text": "甲公司毛利率是４７．３%"}]}, facts)
    assert check({"segments": [{"text": "甲公司毛利率是１２．５%"}]}, facts) == []


def test_empty_subject_does_not_match_every_sentence():
    facts = [{"subject": "", "value": "12.5%"}]
    assert check({"segments": [{"text": "乙公司毛利率12.5%"}]}, facts)


# ---- 第 5 輪驗證的存活突變與未列放行 ----

import pytest


@pytest.mark.parametrize("dash", ["-", "−", "－", "﹣", "–", "—", "‐", "‑", "‒", "⁻"])
def test_every_dash_kind_is_a_minus_sign(dash):
    # fact 是正的 12.5%,腳本用任何一種負號/連字號寫成負數都要擋(F10b:拿掉 – — 會放行)
    assert check(S("甲公司毛利率是%s12.5%%。" % dash), FACTS)


def test_minus_with_space_is_still_negative():
    assert check(S("甲公司毛利率是 - 12.5%。"), FACTS)


def test_range_with_spaces_is_not_negative():
    facts = [{"subject": "甲", "value": "10"}, {"subject": "甲", "value": "12.5%"}]
    assert check(S("甲的成長率是10 - 12.5%。"), facts) == []


def test_parenthesised_number_needs_parenthesised_fact():
    # (12.5%) 可能是會計寫法的負數,不能拿正的 12.5% 背書
    assert check(S("甲公司毛利率(12.5%)。"), FACTS)
    assert check(S("甲公司毛利率(12.5%)。"), [{"subject": "甲公司", "value": "(12.5%)"}]) == []


@pytest.mark.parametrize("text", ["甲公司成長⑦倍。", "甲公司毛利率⁹⁹%。", "甲公司毛利率₉₉%。"])
def test_superscript_and_circled_digits_are_seen(text):
    assert check(S(text), FACTS)


def test_superscript_digits_match_their_plain_fact():
    assert check(S("甲公司毛利率¹²%。"), [{"subject": "甲公司", "value": "12%"}]) == []


def test_description_is_checked():
    # F18:說明欄也是暴露面
    s = S("沒有數字。")
    s["description"] = "暴漲99%"
    assert check(s, FACTS)


@pytest.mark.parametrize("sep", ["。", ". ", "!", "?"])
def test_subject_in_previous_sentence_does_not_count(sep):
    # F19:斷句不能只認換行;半形句點也要斷
    assert check(S("甲公司表現很好%s毛利率是12.5%%。" % sep), FACTS)


def test_decimal_point_does_not_split_sentence():
    assert check(S("甲公司毛利率是12.5%."), FACTS) == []


def test_decimal_is_part_of_the_number():
    # F21:數字正則不含小數時,5.5% 會被拆成 5 和 5%,被 12.5% / 5.9% 的碎片背書
    facts = [{"subject": "甲公司", "value": "12.5%"}, {"subject": "甲公司", "value": "5.9%"}]
    assert check(S("甲公司毛利率5.5%。"), facts)


def test_blank_subject_fact_does_not_make_every_sentence_ambiguous():
    facts = FACTS + [{"subject": "", "value": "30%"}]
    assert check(S("甲公司毛利率是12.5%。"), facts) == []


def test_fullwidth_thousands_comma():
    assert check(S("甲公司營收1，200億。"), [{"subject": "甲公司", "value": "1200億"}]) == []
