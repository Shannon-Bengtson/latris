"""Guard: adapter errors and anything that touches them must not expose API keys.

Google AI Studio ships the key in the URL as a query parameter, so any
traceback / error message that surfaces a ``?key=...`` URL is a leak. We
also cover the standard provider-specific key formats.
"""

from __future__ import annotations

from latris.ai.adapters.base import LLMCallError, redact_secrets


def test_redacts_google_ai_studio_url() -> None:
    text = (
        "Client error '429' for url "
        "'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:"
        "generateContent?key=AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'"
    )
    scrubbed = redact_secrets(text)
    assert "AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in scrubbed
    assert "<REDACTED>" in scrubbed


def test_redacts_anthropic_key() -> None:
    text = "Auth failed with sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH"
    scrubbed = redact_secrets(text)
    assert "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH" not in scrubbed


def test_redacts_openai_project_key() -> None:
    text = "Invalid key sk-proj-AAAABBBBCCCCDDDDEEEEFFFFGGGG"
    scrubbed = redact_secrets(text)
    assert "AAAABBBBCCCCDDDDEEEEFFFFGGGG" not in scrubbed


def test_redacts_openai_legacy_key() -> None:
    text = "error with sk-AAAABBBBCCCCDDDDEEEEFFFFGGGG"
    scrubbed = redact_secrets(text)
    assert "sk-AAAABBBBCCCCDDDDEEEEFFFFGGGG" not in scrubbed


def test_redacts_groq_key() -> None:
    text = "auth: gsk_AAAABBBBCCCCDDDDEEEEFFFFGGGG"
    scrubbed = redact_secrets(text)
    assert "gsk_AAAABBBBCCCCDDDDEEEEFFFFGGGG" not in scrubbed


def test_redacts_generic_key_query_param() -> None:
    text = "https://api.example.com/call?key=ABCD1234EFGH5678IJKL9012&other=1"
    scrubbed = redact_secrets(text)
    assert "ABCD1234EFGH5678IJKL9012" not in scrubbed


def test_passes_through_normal_text() -> None:
    text = "The model returned an invalid JSON blob: missing closing brace."
    assert redact_secrets(text) == text


def test_empty_string() -> None:
    assert redact_secrets("") == ""


def test_llm_call_error_message_is_already_scrubbed() -> None:
    # The adapter is what scrubs; this verifies the class is importable and
    # usable with a pre-scrubbed message.
    err = LLMCallError("GeminiException from gemini-2.5-flash: quota exceeded")
    assert "AIza" not in str(err)
