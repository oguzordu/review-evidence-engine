"""Lokal cumle embedding'i (anlamsal arama icin).

Model lokal calisir; API cagrisi ve kota yoktur. Enjekte edilebilir tasarim:
consensus.gemini_batch_classifier ile ayni desen -- testler sahte encoder verir,
gercek model yalnizca 'slow' testlerde ve calisan uygulamada yuklenir.

Bu modul HTTP katmanini ve veritabanini bilmez.
"""

from typing import Callable

EncoderFn = Callable[[list[str]], list[list[float]]]

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict = {}


def _get_model(model_name: str):
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer

        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def sentence_transformer_encoder(model_name: str = DEFAULT_MODEL) -> EncoderFn:
    """Batch metni L2-normalize edilmis 384-boyutlu vektor listesine ceviren
    bir fonksiyon doner. Model ilk cagrida yuklenir ve cache'lenir."""

    def encode(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _get_model(model_name)
        vectors = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return vectors.tolist()

    return encode
