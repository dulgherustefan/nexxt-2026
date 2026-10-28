"""URM-01: vechimea contului e un fapt obiectiv; vârsta persoanei rămâne interzisă."""

from versoml.shared.rules.packs.urm import prohibited_features


def test_account_age_is_objective_but_person_age_is_not():
    features = ["account_age_days", "in1_account_age_days", "client_age", "age", "holder_gender"]
    assert prohibited_features(features, ["age", "gender"]) == ["client_age", "age", "holder_gender"]
