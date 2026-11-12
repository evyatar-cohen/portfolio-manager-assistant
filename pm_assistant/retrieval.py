"""BM25 over the knowledge documents.

Keyword search is enough for 4 short documents and is fully explainable. Production uses hybrid
(keyword + multilingual embeddings) in Bedrock KB, per the architecture doc.
"""
import math
import re
from collections import Counter

from pm_assistant import data

K1, B = 1.5, 0.75
# Hebrew attaches prepositions/articles to the word ("בסקירת", "השוק"), so index the stripped
# form too. ponytail: naive one-letter prefix strip; a real Hebrew analyzer/embeddings fix this properly.
_PREFIXES = "הבלומשכ"


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in re.findall(r"\w+", text.lower()):
        tokens.append(word)
        if len(word) > 3 and word[0] in _PREFIXES:
            tokens.append(word[1:])
    return tokens


_DOC_TOKENS = {doc_id: Counter(tokenize(d["title"] + " " + d["text"])) for doc_id, d in data.DOCUMENTS.items()}
_AVG_LEN = sum(sum(c.values()) for c in _DOC_TOKENS.values()) / len(_DOC_TOKENS)
_N = len(_DOC_TOKENS)


def _idf(term: str) -> float:
    df = sum(1 for c in _DOC_TOKENS.values() if term in c)
    return math.log(1 + (_N - df + 0.5) / (df + 0.5))


def search(query: str, k: int = 2) -> list[dict]:
    scores = {}
    for doc_id, tf in _DOC_TOKENS.items():
        length = sum(tf.values())
        scores[doc_id] = sum(
            _idf(t) * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * length / _AVG_LEN))
            for t in set(tokenize(query))
            if t in tf
        )
    ranked = sorted((d for d in scores if scores[d] > 0), key=scores.get, reverse=True)[:k]
    return [{"docId": d, **data.DOCUMENTS[d], "score": round(scores[d], 3)} for d in ranked]
