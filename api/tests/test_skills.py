from jobhunt.services.skills import normalise_skill, skill_coverage


def test_aliases_and_normalisation() -> None:
    assert normalise_skill("Postgres") == "postgresql"
    assert normalise_skill("K8s") == "kubernetes"
    assert normalise_skill("Node.js") == "nodejs"
    assert normalise_skill("  Amazon Web Services ") == "aws"
    assert normalise_skill("C#") == "c#"


def test_coverage_matches_profile_skills_and_evidence_text() -> None:
    cov = skill_coverage(
        ["Python", "Postgres", "Kafka", "Rust", "Go"],
        ["python", "PostgreSQL"],
        ["Built a Kafka pipeline.", "Wrote Django services.", "Go-to person for incidents."],
    )
    assert cov.matched == ["Python", "Postgres", "Kafka"]
    assert cov.missing == ["Rust", "Go"]  # "Go-to" must not count as the Go language
    assert cov.ratio == 0.6


def test_coverage_with_no_requirements() -> None:
    cov = skill_coverage([], ["python"], [])
    assert cov.ratio is None and cov.required == []
