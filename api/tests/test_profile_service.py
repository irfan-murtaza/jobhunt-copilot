from helpers import load_sample
from jobhunt.services.profile import build_evidence


def test_sample_profile_is_valid() -> None:
    doc = load_sample()
    assert doc.name == "Casey Rivera"
    assert len(doc.roles) == 2


def test_evidence_covers_every_bullet_project_and_skill_with_stable_paths() -> None:
    doc = load_sample()
    items = build_evidence(doc)
    kinds = {kind: sum(1 for i in items if i.kind == kind) for kind in {i.kind for i in items}}
    total_bullets = sum(len(r.bullets) for r in doc.roles) + sum(
        len(p.bullets) for p in doc.projects
    )
    assert kinds["bullet"] == total_bullets
    assert kinds["project"] == len(doc.projects)
    assert kinds["skill"] == len(doc.skills)
    assert kinds["summary"] == 1

    first_bullet = next(i for i in items if i.path == "roles/0/bullets/0")
    assert first_bullet.text.startswith("Led migration of a Django monolith")
    assert (
        first_bullet.context
        == "Senior Backend Engineer at Northwind Analytics (2021-03 to present)"
    )
    assert first_bullet.embedding_text.startswith("Senior Backend Engineer at Northwind")

    # Paths are unique so a generated claim can cite exactly one fact.
    assert len({i.path for i in items}) == len(items)


def test_build_evidence_is_deterministic() -> None:
    doc = load_sample()
    assert [i.path for i in build_evidence(doc)] == [i.path for i in build_evidence(doc)]
