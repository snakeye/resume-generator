# Adding An LLM Provider

Do not add a provider until there is a concrete user need and a way to test it.

An implementation must:

1. satisfy the small `LLMProvider` protocol;
2. accept explicit endpoint, model, key, and timeout configuration;
3. support the project's structured JSON contract;
4. normalize usage metadata;
5. classify retryable and permanent errors;
6. preserve provider and model identity in run metadata;
7. pass shared contract tests using mocked HTTP;
8. document privacy and setup differences.

It must not silently fall back to another provider or model. Provider-specific
prompt forks require evidence that a shared prompt cannot meet the contract.
