"""
Multi-factor credibility scoring for retrieved documents.

Formula:
  total = 0.35 * domain_score
        + 0.25 * recency_score
        + 0.25 * content_quality_score
        + 0.15 * relevance_boost
All sub-scores in [0.0, 1.0].
"""
import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CredibilityResult:
    total_score: float
    domain_score: float
    recency_score: float
    content_quality_score: float
    source_type: str
    breakdown: dict


class CredibilityScorer:
    # Tier 1: Highest-authority sources (peer-reviewed / official research)
    TIER1_DOMAINS = {
        "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org",
        "ieee.org", "acm.org", "dl.acm.org", "scholar.google.com",
        "research.google", "ai.meta.com", "openai.com", "anthropic.com",
        "deepmind.com", "huggingface.co", "papers.nips.cc", "mlsys.org",
        "semanticscholar.org", "proceedings.mlr.press",
    }
    # Tier 2: High-quality tech, edu, and media
    TIER2_DOMAINS = {
        "github.com", "stackoverflow.com", "medium.com", "towardsdatascience.com",
        "distill.pub", "lilianweng.github.io", "colah.github.io",
        "techcrunch.com", "wired.com", "arstechnica.com", "theverge.com",
        "hbr.org", "mit.edu", "stanford.edu", "berkeley.edu", "cmu.edu",
        "harvard.edu", "oxford.ac.uk", "cambridge.org", "springer.com",
        "sciencedirect.com", "jstor.org",
    }
    # Tier 3: General quality / community
    TIER3_DOMAINS = {
        "wikipedia.org", "reddit.com", "news.ycombinator.com",
        "blog.tensorflow.org", "pytorch.org", "docs.python.org",
        "developer.mozilla.org", "docs.microsoft.com",
    }
    LOW_QUALITY_SIGNALS = [
        "click here", "buy now", "limited time offer",
        "sponsored content", "advertisement", "affiliate link",
        "subscribe to our newsletter", "cookie policy",
    ]

    def score(self, doc: object) -> float:
        """Score a RetrievedDoc (or any object with .content and .metadata)."""
        domain = doc.metadata.get("domain", "")
        content = doc.content if hasattr(doc, "content") else ""
        crawled_at = doc.metadata.get("crawled_at", 0)
        keyword_hits = doc.metadata.get("keyword_hits", 0)

        ds = self._score_domain(domain)
        rs = self._score_recency(crawled_at)
        qs = self._score_content_quality(content)
        rb = min(keyword_hits / 10.0, 1.0)

        total = 0.35 * ds + 0.25 * rs + 0.25 * qs + 0.15 * rb
        return round(total, 3)

    def score_dict(self, doc: object) -> CredibilityResult:
        """Return full breakdown."""
        domain = doc.metadata.get("domain", "")
        content = doc.content if hasattr(doc, "content") else ""
        crawled_at = doc.metadata.get("crawled_at", 0)
        keyword_hits = doc.metadata.get("keyword_hits", 0)

        ds = self._score_domain(domain)
        rs = self._score_recency(crawled_at)
        qs = self._score_content_quality(content)
        rb = min(keyword_hits / 10.0, 1.0)
        total = round(0.35 * ds + 0.25 * rs + 0.25 * qs + 0.15 * rb, 3)

        tier = self._get_tier(domain)
        return CredibilityResult(
            total_score=total,
            domain_score=ds,
            recency_score=rs,
            content_quality_score=qs,
            source_type=tier,
            breakdown={
                "domain": round(ds, 3),
                "recency": round(rs, 3),
                "content_quality": round(qs, 3),
                "relevance_boost": round(rb, 3),
            },
        )

    # ── Sub-scorers ────────────────────────────────────────────────────

    def _get_tier(self, domain: str) -> str:
        d = domain.lower()
        if any(t in d for t in self.TIER1_DOMAINS):
            return "tier1_academic"
        if any(t in d for t in self.TIER2_DOMAINS):
            return "tier2_quality"
        if any(t in d for t in self.TIER3_DOMAINS):
            return "tier3_general"
        if d.endswith(".edu") or d.endswith(".gov"):
            return "tier2_quality"
        return "unknown"

    def _score_domain(self, domain: str) -> float:
        d = domain.lower()
        if any(t in d for t in self.TIER1_DOMAINS):
            return 1.0
        if any(t in d for t in self.TIER2_DOMAINS):
            return 0.75
        if any(t in d for t in self.TIER3_DOMAINS):
            return 0.55
        if d.endswith(".edu") or d.endswith(".gov"):
            return 0.70
        if d.endswith(".org"):
            return 0.50
        return 0.30  # Unknown domain — penalise

    def _score_recency(self, crawled_at: float) -> float:
        if not crawled_at:
            return 0.40
        age_days = (datetime.now().timestamp() - float(crawled_at)) / 86400
        if age_days < 30:
            return 1.00
        elif age_days < 90:
            return 0.85
        elif age_days < 365:
            return 0.65
        elif age_days < 730:
            return 0.45
        return 0.25

    def _score_content_quality(self, content: str) -> float:
        score = 0.50

        # Penalise low-quality signals
        cl = content.lower()
        penalty = sum(0.10 for p in self.LOW_QUALITY_SIGNALS if p in cl)
        score -= min(penalty, 0.40)

        # Length bonus — substantive content tends to be longer
        word_count = len(content.split())
        if word_count > 500:
            score += 0.15
        elif word_count > 200:
            score += 0.08

        # Academic writing markers (citations)
        citations = len(re.findall(r"\(\d{4}\)|\[\d+\]|et al\.", content))
        if citations >= 3:
            score += 0.20
        elif citations >= 1:
            score += 0.10

        # Technical density (code, formulas)
        if re.search(r"def |import |class |```", content):
            score += 0.10

        return round(min(max(score, 0.0), 1.0), 3)


credibility_scorer = CredibilityScorer()
