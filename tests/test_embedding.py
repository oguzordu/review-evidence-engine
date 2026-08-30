import pytest

from review_evidence.embedding import sentence_transformer_encoder


@pytest.mark.slow
def test_encoder_returns_384_dim_normalized_vectors():
    encode = sentence_transformer_encoder()

    vectors = encode(["urun cok kotu", "urun harika"])

    assert len(vectors) == 2
    assert all(len(v) == 384 for v in vectors)
    norm = sum(x * x for x in vectors[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-3


@pytest.mark.slow
def test_encoder_places_synonyms_closer_than_antonyms():
    encode = sentence_transformer_encoder()
    kotu, berbat, harika = encode(["urun kotu", "urun berbat", "urun harika"])

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    assert dot(kotu, berbat) > dot(kotu, harika)
