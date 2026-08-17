import pytest

from backend.app.methodological_quality import (
    DEFAULT_DOMAINS,
    calculate_overall_rating,
    validate_ai_suggestion,
    validate_domains,
)


CHUNKS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "page_number": 4,
        "chunk_text": "The dataset contains 240 instances and the evaluation uses cross-validation.",
    }
]


def _raw(response="yes", quote="The dataset contains 240 instances"):
    return {
        "domains": [
            {
                "domain_code": DEFAULT_DOMAINS[0]["code"],
                "response": response,
                "rationale": "A amostra foi descrita.",
                "confidence": 0.9,
                "evidence": [{"chunk_id": CHUNKS[0]["id"], "quote": quote}],
            }
        ],
        "overall_rationale": "Síntese proposta pela IA.",
    }


def test_ai_suggestion_preserves_only_literal_traceable_quote():
    result = validate_ai_suggestion(_raw(), CHUNKS, DEFAULT_DOMAINS)

    first = result["domains"][0]
    assert first["response"] == "yes"
    assert first["evidence"][0]["page"] == 4
    assert first["evidence"][0]["chunk_id"] == CHUNKS[0]["id"]


def test_yes_or_no_without_literal_source_is_downgraded_to_uncertain():
    result = validate_ai_suggestion(
        _raw(response="no", quote="This sentence does not exist."),
        CHUNKS,
        DEFAULT_DOMAINS,
    )

    first = result["domains"][0]
    assert first["response"] == "uncertain"
    assert first["confidence"] == 0.0
    assert result["validation_warnings"]


def test_overall_rating_flags_critical_negative_as_high():
    responses = [
        {"domain_code": domain["code"], "response": "yes"}
        for domain in DEFAULT_DOMAINS
    ]
    responses[1]["response"] = "no"

    assert calculate_overall_rating(responses, DEFAULT_DOMAINS) == "high"


def test_overall_rating_exposes_information_uncertainty():
    responses = [
        {"domain_code": domain["code"], "response": "yes"}
        for domain in DEFAULT_DOMAINS
    ]
    responses[0]["response"] = "uncertain"
    responses[3]["response"] = "uncertain"

    assert calculate_overall_rating(responses, DEFAULT_DOMAINS) == "uncertain"


def test_instrument_rejects_duplicate_domain_codes():
    with pytest.raises(ValueError, match="código único"):
        validate_domains([DEFAULT_DOMAINS[0], DEFAULT_DOMAINS[0]])
