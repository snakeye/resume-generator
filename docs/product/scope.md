# Product Scope

## MVP

- one candidate and one repository;
- one local foreground runner;
- one request at a time;
- GitHub Issue Form input;
- local YAML profile;
- DeepSeek as the working LLM provider;
- English resume requests only;
- JSON, Markdown, TeX, PDF, DOCX, report, and metadata output;
- human review through Pull Requests;
- macOS and Linux, with Windows through WSL;
- synthetic CI without live LLM calls.

## Not MVP

- hosted web service or GUI;
- GitHub Actions generation using the real profile;
- multiple candidates or repositories;
- concurrent or distributed workers;
- database, queue, webhooks, or containers;
- automatic PR review handling or merge;
- automatic job applications;
- browser automation;
- runtime plugin system;
- support guarantees for OpenAI or Ollama adapters.
