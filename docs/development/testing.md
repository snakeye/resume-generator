# Testing

Tests use pytest and synthetic data. Mandatory CI never calls a real LLM.

## Test Shape

Each test verifies one condition or one concrete behavior:

```python
def test_skips_pull_requests():
    issue = make_issue(pull_request=True)

    result = select_issue([issue])

    assert result is None
```

Use function tests, Arrange-Act-Assert, minimal inputs, and behavior-focused
names. Multiple physical assertions are acceptable only when they describe
one indivisible result.

Do not use a single test for parsing, labels, generation, Git, and publishing.
An end-to-end test is the explicit exception and verifies one complete user
journey.

## Test Doubles

Use fakes at external boundaries:

- fake LLM provider;
- fake GitHub client;
- temporary Git repository;
- fake clock or sleeper when needed.
- fake LaTeX compiler and PDF text extractor;

Do not mock small internal functions or assert private call sequences. Test
observable results.

## Layers

- unit tests cover deterministic functions;
- contract tests verify Pydantic models and provider boundaries;
- integration tests cover runner orchestration with fakes;
- regression tests cover prompt injection and factual drift;
- end-to-end tests cover the synthetic Issue-to-PR flow.

Live provider tests are optional, explicit, and excluded from normal CI.
