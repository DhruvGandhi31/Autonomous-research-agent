"""
Document processing pipeline:
  Raw content → Quality filter → Language filter → Clean →
  Semantic chunk (sentence-boundary-aware, with overlap) →
  Entity extraction (spaCy NER) → ProcessedChunk

spaCy and langdetect are optional — pipeline degrades gracefully.
"""
import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from loguru import logger

# ── Optional NLP deps ──────────────────────────────────────────────────────────
_nlp = None
_LANGDETECT_OK = False

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model loaded: en_core_web_sm")
        except Exception as e:
            logger.warning(f"spaCy unavailable (NER disabled): {e}")
            _nlp = False   # sentinel — tried but failed
    return _nlp if _nlp is not False else None

def _check_langdetect():
    global _LANGDETECT_OK
    if not _LANGDETECT_OK:
        try:
            from langdetect import detect
            _LANGDETECT_OK = True
        except ImportError:
            logger.warning("langdetect unavailable (language filter disabled)")
    return _LANGDETECT_OK


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ProcessedChunk:
    chunk_id: str
    source_url: str
    content: str
    token_count: int
    chunk_index: int
    total_chunks: int
    entities: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ── Processor ─────────────────────────────────────────────────────────────────

class DocumentProcessor:
    """
    Converts raw fetched page data into clean, enriched ProcessedChunks
    ready for embedding and indexing.
    """
    NAV_BOILERPLATE = [
        "cookie policy", "terms of service", "404 not found",
        "javascript required", "enable cookies", "privacy policy",
    ]

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process(self, raw: dict) -> list[ProcessedChunk]:
        """
        raw must contain at least: {"url": str, "content": str}
        Optional keys: {"title": str, "crawled_at": float, "keyword_hits": int}
        """
        text = raw.get("content", "").strip()
        url = raw.get("url", "")

        if not self._passes_quality_filter(text):
            return []

        if not self._passes_language_filter(text):
            return []

        text = self._clean_text(text)
        chunks = self._semantic_chunk(text)
        if not chunks:
            return []

        nlp = _get_nlp()
        domain = _extract_domain(url)
        processed: list[ProcessedChunk] = []

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.sha256(f"{url}:{i}".encode()).hexdigest()[:16]

            entities: list[str] = []
            if nlp:
                try:
                    doc = nlp(chunk[:1000])
                    entities = list({
                        ent.text for ent in doc.ents
                        if ent.label_ in {"ORG", "PERSON", "GPE", "PRODUCT", "EVENT", "LAW", "WORK_OF_ART"}
                    })
                except Exception:
                    pass

            processed.append(ProcessedChunk(
                chunk_id=chunk_id,
                source_url=url,
                content=chunk,
                token_count=len(chunk.split()),
                chunk_index=i,
                total_chunks=len(chunks),
                entities=entities,
                metadata={
                    "title": raw.get("title", ""),
                    "crawled_at": raw.get("crawled_at", time.time()),
                    "domain": domain,
                    "keyword_hits": raw.get("keyword_hits", 0),
                    "source": raw.get("source", "web"),
                },
            ))

        return processed

    # ── Filters ────────────────────────────────────────────────────────

    def _passes_quality_filter(self, text: str) -> bool:
        if len(text.split()) < 100:
            return False
        tl = text.lower()
        boilerplate_hits = sum(1 for kw in self.NAV_BOILERPLATE if kw in tl)
        if boilerplate_hits >= 2:
            return False
        paragraphs = [p for p in text.split("\n") if len(p.strip()) > 20]
        if len(paragraphs) < 3:
            return False
        return True

    def _passes_language_filter(self, text: str) -> bool:
        """English-only gate. Passes when langdetect is unavailable."""
        if not _check_langdetect():
            return True
        try:
            from langdetect import detect, LangDetectException
            return detect(text[:2000]) == "en"
        except Exception:
            return True  # Don't drop content if detection fails

    # ── Processing ─────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"https?://\S+", "", text)       # Strip URLs
        text = re.sub(r"\[.*?\]", "", text)             # Strip bracket refs
        text = re.sub(r"\s+", " ", text)                # Normalise whitespace
        return text.strip()

    def _semantic_chunk(self, text: str) -> list[str]:
        """
        Split on sentence boundaries, accumulate up to chunk_size words,
        then carry forward chunk_overlap words into the next chunk.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current: list[str] = []
        count = 0

        for sent in sentences:
            words = len(sent.split())
            if count + words > self.chunk_size and current:
                chunks.append(" ".join(current))
                # Carry overlap
                overlap: list[str] = []
                overlap_count = 0
                for s in reversed(current):
                    w = len(s.split())
                    if overlap_count + w <= self.chunk_overlap:
                        overlap.insert(0, s)
                        overlap_count += w
                    else:
                        break
                current = overlap
                count = overlap_count
            current.append(sent)
            count += words

        if current:
            chunks.append(" ".join(current))

        return [c for c in chunks if len(c.split()) >= 20]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


document_processor = DocumentProcessor()
