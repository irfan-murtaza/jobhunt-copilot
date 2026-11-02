"""Skill matching between a posting's requirements and the candidate's profile.

Deliberately simple and transparent: lower-case, strip punctuation, map common aliases,
then check for an exact skill match or a whole-word mention in any evidence text. The
LLM judge handles the fuzzy cases; this stage only has to be explainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALIASES: dict[str, str] = {
    "postgres": "postgresql",
    "psql": "postgresql",
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "golang": "go",
    "node": "nodejs",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    "react.js": "react",
    "reactjs": "react",
    "vue.js": "vue",
    "vuejs": "vue",
    "next.js": "nextjs",
    "amazon web services": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    "ci/cd": "cicd",
    "ci cd": "cicd",
    "rest apis": "rest",
    "restful apis": "rest",
    "rest api": "rest",
    "large language models": "llm",
    "llms": "llm",
    "machine learning": "ml",
    "gen ai": "generative ai",
    "genai": "generative ai",
    "c sharp": "c#",
    "dotnet": ".net",
    "mongo": "mongodb",
    "elastic": "elasticsearch",
    "tf": "terraform",
}

_PUNCT = re.compile(r"[^\w#+./ -]")


def normalise_skill(skill: str) -> str:
    key = skill.strip().lower()
    key = _PUNCT.sub("", key)
    key = re.sub(r"\s+", " ", key).strip()
    return ALIASES.get(key, key)


def _mentioned(skill: str, text: str) -> bool:
    pattern = r"(?<![\w#+.-])" + re.escape(skill) + r"(?![\w#+-])"
    return re.search(pattern, text, re.IGNORECASE) is not None


@dataclass(slots=True)
class SkillCoverage:
    required: list[str]
    matched: list[str]
    missing: list[str]

    @property
    def ratio(self) -> float | None:
        return len(self.matched) / len(self.required) if self.required else None


def skill_coverage(
    required: list[str], profile_skills: list[str], evidence_texts: list[str]
) -> SkillCoverage:
    have = {normalise_skill(s) for s in profile_skills}
    corpus = "\n".join(evidence_texts)
    corpus_aliased = corpus
    for alias, canonical in ALIASES.items():
        if alias in corpus.lower():
            corpus_aliased += f"\n{canonical}"
    matched: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw in required:
        key = normalise_skill(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        if key in have or _mentioned(key, corpus_aliased):
            matched.append(raw)
        else:
            missing.append(raw)
    return SkillCoverage(
        required=list(seen) and [r for r in required if normalise_skill(r) in seen],
        matched=matched,
        missing=missing,
    )
