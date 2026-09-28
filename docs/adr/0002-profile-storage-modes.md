# ADR-0002: Profile Storage Modes

Status: Accepted

## Context

The profile contains sensitive personal and professional information. Some
users may still want private Git history and synchronization.

## Decision

The files in `data/profile/` are ignored and local by default. Tracking them in
Git is an explicit opt-in permitted only after verifying private repository
visibility and warning about permanent history.

Public repositories may use only the synthetic example profile.

## Consequences

The application uses one canonical profile directory and a main profile path.
Local mode is safer;
private Git mode is convenient but increases exposure. Setup and diagnostics
must prevent accidental use of real data in a public repository.
