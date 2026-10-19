import pytest
from gateway import (
    detect_user_persona,
    detect_response_archetype,
    ARCHETYPE_EXECUTIVE_SUMMARY,
    ARCHETYPE_STRUCTURED_AUDIT,
    ARCHETYPE_CODE_ENGINEERING,
    ARCHETYPE_CONCEPTUAL_MENTOR,
    ARCHETYPE_MULTI_TURN_CONTINUATION,
)

def test_brevity_and_urgency_directive():
    p1 = "broooo what is ragi? quick answer"
    d1 = detect_user_persona(p1)
    assert "ultra-direct, punchy, conversational replies with zero corporate fluff" in d1
    assert "Lead directly with the answer in sentence 1" in d1

    p2 = "tell fast what is the price"
    d2 = detect_user_persona(p2)
    assert "ultra-direct, punchy, conversational replies with zero corporate fluff" in d2

    p3 = "why?"
    d3 = detect_user_persona(p3)
    assert "ultra-direct, punchy, conversational replies with zero corporate fluff" in d3


def test_frustration_and_confusion_directive():
    p1 = "i told you already, i am not getting this, you are not teaching well, explain simply"
    d1 = detect_user_persona(p1)
    assert "User is experiencing friction. Validate immediately, avoid defensiveness" in d1
    assert "pivot to concrete, simplified real-world analogies" in d1

    p2 = "this makes no sense, you're not teaching well"
    d2 = detect_user_persona(p2)
    assert "User is experiencing friction. Validate immediately, avoid defensiveness" in d2


def test_academic_and_deep_research_directive():
    p1 = "Derive the backpropagation algorithm with formal mathematical proofs and computational complexity."
    d1 = detect_user_persona(p1)
    assert "User wants rigorous, structured, academic depth" in d1
    assert "Use precise domain terminology, step-by-step reasoning, and structured markdown sections" in d1


def test_data_and_tabular_lookups_directive():
    p1 = "Provide a clean markdown table comparing wheat and rice nutritional values"
    d1 = detect_user_persona(p1)
    assert "User seeks structured precision. Use clean Markdown tables" in d1


def test_language_mirroring_kannada_and_kanglish():
    # Kannada Unicode script
    p_kannada = "ನಮಸ್ಕಾರ, ರಾಗಿ ಬೆಳೆಯ ಬಗ್ಗೆ ಮಾಹಿತಿ ನೀಡಿ"
    d_kannada = detect_user_persona(p_kannada)
    assert "User communicates in Kannada / Kanglish (Kannada in Roman script)" in d_kannada
    assert "Mirror their exact linguistic preference naturally and warmly" in d_kannada

    # Kanglish Roman phonetic script
    p_kanglish = "Namaskara, ragi bele hege madodu swalpa heli"
    d_kanglish = detect_user_persona(p_kanglish)
    assert "User communicates in Kannada / Kanglish (Kannada in Roman script)" in d_kanglish


def test_multi_turn_memory_guard():
    history = [
        {"role": "user", "content": "What is drip irrigation?"},
        {"role": "assistant", "content": "Drip irrigation saves water."}
    ]
    # Follow up with nudge
    d_followup = detect_user_persona("why?", recent_history=history)
    assert "ultra-direct, punchy, conversational replies with zero corporate fluff" in d_followup

    # Follow up in Kanglish context
    kanglish_history = [
        {"role": "user", "content": "Namaskara"},
        {"role": "assistant", "content": "Namaskara! Hege sahayaka madli?"}
    ]
    d_kanglish_followup = detect_user_persona("yenu samachara", recent_history=kanglish_history)
    assert "Kannada / Kanglish" in d_kanglish_followup


def test_zero_shot_archetype_detection():
    # Executive summary
    assert detect_response_archetype("price of tomato in kolar") == ARCHETYPE_EXECUTIVE_SUMMARY
    assert detect_response_archetype("tell fast what is the rate") == ARCHETYPE_EXECUTIVE_SUMMARY

    # Structured audit
    assert detect_response_archetype("is Aadhaar present in the document?") == ARCHETYPE_STRUCTURED_AUDIT
    assert detect_response_archetype("compare wheat and barley yields and prices") == ARCHETYPE_STRUCTURED_AUDIT

    # Code engineering
    assert detect_response_archetype("def calculate_fibonacci(n): pass") == ARCHETYPE_CODE_ENGINEERING
    assert detect_response_archetype("Traceback (most recent call last): File 'gateway.py', line 12 TypeError") == ARCHETYPE_CODE_ENGINEERING

    # Conceptual mentor
    assert detect_response_archetype("explain like i'm 5 what is quantum computing") == ARCHETYPE_CONCEPTUAL_MENTOR
    assert detect_response_archetype("i am not getting this, explain how attention works simply") == ARCHETYPE_CONCEPTUAL_MENTOR

    # Multi-turn continuation
    history = [{"role": "user", "content": "What is drip irrigation?"}]
    assert detect_response_archetype("broooo", recent_history=history) == ARCHETYPE_MULTI_TURN_CONTINUATION
    assert detect_response_archetype("why?", recent_history=history) == ARCHETYPE_MULTI_TURN_CONTINUATION
