from review_evidence.text import collapse_repeats, fold_ascii, normalize, turkish_lower


def test_turkish_lower_handles_dotless_i():
    assert turkish_lower("IŞIK") == "ışık"


def test_turkish_lower_handles_dotted_i():
    assert turkish_lower("İSTANBUL") == "istanbul"


def test_collapse_repeats_shortens_long_runs():
    assert collapse_repeats("çoookkk") == "çookk"


def test_collapse_repeats_leaves_double_letters_alone():
    assert collapse_repeats("dikkat") == "dikkat"


def test_fold_ascii_removes_turkish_characters():
    assert fold_ascii("çğıöşü") == "cgiosu"


def test_normalize_collapses_whitespace_and_lowercases():
    assert normalize("  ÜRÜN   ÇOK   GÜZEL  ") == "ürün çok güzel"


    