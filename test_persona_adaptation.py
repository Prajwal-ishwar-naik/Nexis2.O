import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000/api/chat"

test_cases = [
    {
        "name": "Brevity & Urgency",
        "payload": {
            "query": "broooo quick answer what is photosynthesis?",
            "session_id": "test_persona_brevity_001"
        },
        "expected_directive_substr": "ultra-direct, punchy, conversational replies with zero corporate fluff"
    },
    {
        "name": "Frustration / Confusion",
        "payload": {
            "query": "i told you already, i am not getting this, you are not teaching well, explain simply",
            "session_id": "test_persona_frustration_001"
        },
        "expected_directive_substr": "experiencing friction. Validate immediately, avoid defensiveness"
    },
    {
        "name": "Academic / Deep Research",
        "payload": {
            "query": "Provide a formal mathematical derivation of the backpropagation algorithm and its computational complexity.",
            "session_id": "test_persona_academic_001"
        },
        "expected_directive_substr": "rigorous, structured, academic depth"
    },
    {
        "name": "Data & Tabular Lookups",
        "payload": {
            "query": "Provide a clean markdown table comparing wheat and barley nutrition values and soil types.",
            "session_id": "test_persona_tabular_001"
        },
        "expected_directive_substr": "structured precision. Use clean Markdown tables"
    },
    {
        "name": "Language Mirroring (Kannada Script)",
        "payload": {
            "query": "ನಮಸ್ಕಾರ, ರಾಗಿ ಬೆಳೆಯ ಬಗ್ಗೆ ಮಾಹಿತಿ ನೀಡಿ",
            "session_id": "test_persona_kannada_001"
        },
        "expected_directive_substr": "Kannada / Kanglish"
    },
    {
        "name": "Language Mirroring (Kanglish)",
        "payload": {
            "query": "Namaskara, ragi bele hege madodu swalpa heli?",
            "session_id": "test_persona_kanglish_001"
        },
        "expected_directive_substr": "Kannada / Kanglish"
    },
    {
        "name": "Multi-turn Persona Preservation",
        "payload": {
            "query": "why?",
            "session_id": "test_persona_multiturn_001",
            "history": [
                {"role": "user", "content": "What is drip irrigation?"},
                {"role": "assistant", "content": "Drip irrigation delivers water directly to plant roots using emitters to save water."}
            ]
        },
        "expected_directive_substr": "ultra-direct, punchy, conversational replies"
    }
]

print("=== Running Persona Adaptation Test Suite ===")
import time
all_passed = True

for tc in test_cases:
    time.sleep(1.5)
    print(f"\nTesting: {tc['name']}...")
    try:
        resp = requests.post(BASE_URL, json=tc["payload"], timeout=60)
        if resp.status_code != 200:
            print(f"❌ Failed: HTTP {resp.status_code} - {resp.text}")
            all_passed = False
            continue
        
        data = resp.json()
        directive = data.get("adaptive_persona", "")
        response_text = data.get("response", "")
        
        print(f"  Directive Injected: \"{directive}\"")
        print(f"  Response Preview: {response_text[:160]}...")

        if tc["expected_directive_substr"] in directive:
            print(f"  ✅ PASS: Directive matched '{tc['expected_directive_substr']}'")
        else:
            print(f"  ❌ FAIL: Expected '{tc['expected_directive_substr']}' not found in '{directive}'")
            all_passed = False

    except Exception as e:
        print(f"❌ Exception: {e}")
        all_passed = False

print("\n" + ("=" * 45))
if all_passed:
    print("🎉 ALL PERSONA ADAPTATION TESTS PASSED!")
    sys.exit(0)
else:
    print("❌ SOME TESTS FAILED.")
    sys.exit(1)
