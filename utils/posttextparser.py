import os
import re
import time
from typing import List

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

from utils.console import print_step
from utils.voice import sanitize_text


def _fallback_sentence_split(text: str) -> List[str]:
    """Fallback sentence splitter when spacy is not available."""
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if s.strip()]


# working good
def posttextparser(obj, *, tried: bool = False) -> List[str]:
    text: str = re.sub("\n", " ", obj)

    if not SPACY_AVAILABLE:
        return _fallback_sentence_split(text)

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError as e:
        if not tried:
            os.system("python -m spacy download en_core_web_sm")
            time.sleep(5)
            return posttextparser(obj, tried=True)
        print_step(
            "The spacy model can't load. Falling back to regex-based sentence splitting. Install with: python -m spacy download en_core_web_sm"
        )
        return _fallback_sentence_split(text)

    doc = nlp(text)

    newtext: list = []

    for line in doc.sents:
        if sanitize_text(line.text):
            newtext.append(line.text)

    return newtext
