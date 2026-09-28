# LLM Providers

The pipeline depends on one small structured-output contract. The first working
implementation is DeepSeek.

```python
class LLMProvider(Protocol):
    def generate_json(self, request: LLMRequest) -> LLMResponse: ...
```

The protocol is justified by the planned production provider and the fake used
by tests. It must not grow into a plugin framework.

## First-Release Target

- `deepseek`: the only implemented and supported provider;
- `openai`: an explicit unsupported stub;
- `ollama`: an explicit unsupported stub.

Unsupported providers fail with an actionable message. The system never
silently changes provider or model. `LLM_PROVIDER` selects the provider and
`LLM_MODEL` optionally overrides the DeepSeek model; otherwise the safe default
is `deepseek-chat`.

Environment configuration is loaded at the application boundary by the
Pydantic Settings model. It reads `.env` through `python-dotenv`, while real
process environment variables take precedence. Provider implementations receive
validated settings and never read `os.environ` directly.

## Shared Behavior

A provider implementation owns:

- endpoint, API key, model, and HTTP session;
- timeout and conservative retry behavior;
- structured JSON response handling;
- normalized token usage and response metadata;
- safe error classification.

The DeepSeek adapter uses the standard library HTTP client, requests JSON
output explicitly, retries rate-limit and server failures with bounded
backoff, and never includes prompts, responses, or API keys in its errors.

Prompts remain provider-independent resources. Stable system and task messages
are separated from the run-specific JSON payload.
