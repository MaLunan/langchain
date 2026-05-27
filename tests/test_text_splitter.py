import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from text_splitter import split_into_scenes


def test_groups_two_short_sentences():
    scenes = split_into_scenes("今天天气很好。明天也是晴天。")
    assert scenes == ["今天天气很好。明天也是晴天。"]


def test_odd_sentence_count_last_is_alone():
    scenes = split_into_scenes("第一句。第二句。第三句。")
    assert scenes == ["第一句。第二句。", "第三句。"]


def test_long_pair_splits_individually():
    long = "A" * 150
    text = f"{long}。{long}。"
    scenes = split_into_scenes(text, max_chars=200)
    assert len(scenes) == 2
    assert scenes[0] == f"{long}。"
    assert scenes[1] == f"{long}。"


def test_skips_blank_tokens():
    scenes = split_into_scenes("   \n\n  ")
    assert scenes == []


def test_question_and_exclamation_as_separators():
    scenes = split_into_scenes("真的吗！没错吧？当然！不对吗？")
    assert len(scenes) == 2
    assert "真的吗！没错吧？" in scenes[0]
