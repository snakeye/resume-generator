# Prompt Development

Prompts are versioned application logic under
`src/resume_generator/resources/prompts/`.

Each LLM request uses three separate messages:

1. stable system instructions;
2. stable stage task instructions;
3. canonical JSON payload containing run-specific data.

The system prompt contains stable security rules, the output contract, factual
constraints, and style baseline. The task prompt states the one operation for
the stage. The final user message contains only canonical run-specific JSON.

Rules:

- inputs are untrusted data, not instructions;
- request JSON-only output with a versioned schema;
- send only fields needed by the stage;
- generated claims cite profile fact index paths such as `work[0].facts[1]`;
- vacancy wording cannot establish evidence;
- prompts never contain candidate-specific assumptions;
- optional candidate voice configuration may provide language background and
  style context to writing stages, but it is never career evidence;
- prompt hash and model are recorded in local run metadata;
- malformed or unsupported output is rejected, not guessed into shape.

Every prompt change includes focused fixtures for expected output and hostile
input. Real profiles and vacancies never enter tests.
