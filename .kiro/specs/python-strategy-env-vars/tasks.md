# Implementation Plan: Per-Strategy Environment Variables

## Overview

This implementation adds configurable per-strategy environment variables to the Python Strategy system. The work is split into backend validation/storage, subprocess environment injection, frontend UI components, and API wiring. Each task builds incrementally — starting with pure utility functions, then route modifications, then frontend components, and finally integration.

## Tasks

- [x] 1. Implement backend validation and environment merge utilities
  - [x] 1.1 Create `validate_env_vars` and `build_subprocess_env` helper functions
    - Add a new file `utils/strategy_env.py` (or add to existing utils) with:
      - `validate_env_vars(env_vars)` → returns `(is_valid, error_message, sanitized_dict)`
      - `build_subprocess_env(strategy_env_vars)` → returns merged environment dict
    - `validate_env_vars`: accepts any input, returns True+empty dict for None, validates dict with string keys/values, filters empty values
    - `build_subprocess_env`: copies `os.environ`, overlays strategy vars (converting all values to strings)
    - _Requirements: 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 5.4, 5.5_

  - [ ]* 1.2 Write property tests for `validate_env_vars` (Property 6: API Env Vars Type Validation)
    - **Property 6: API Env Vars Type Validation**
    - **Validates: Requirements 5.4, 5.5**
    - Use Hypothesis to generate arbitrary inputs and verify acceptance iff input is a dict with all-string keys and all-string values (or None)

  - [ ]* 1.3 Write property tests for `build_subprocess_env` (Property 3: Environment Merge Correctness)
    - **Property 3: Environment Merge Correctness**
    - **Validates: Requirements 4.1, 4.3, 4.4, 4.5**
    - Use Hypothesis to generate parent env dicts and strategy env dicts, verify: all parent keys present, all strategy keys present, strategy overrides parent for conflicts, all values are strings

  - [ ]* 1.4 Write property test for empty value filtering (Property 2: Empty Value Filtering)
    - **Property 2: Empty Value Filtering**
    - **Validates: Requirements 3.6**
    - Use Hypothesis to generate dicts with a mix of empty and non-empty string values, verify sanitized output excludes all empty-value entries

- [x] 2. Update backend routes for env_vars storage
  - [x] 2.1 Update `new_strategy()` route (POST `/python/new`) to accept and store env_vars
    - Parse `env_vars` from `request.form.get("env_vars", "{}")`
    - JSON-decode, validate via `validate_env_vars()`
    - On validation failure return 400 with error message
    - Store sanitized dict in `STRATEGY_CONFIGS[strategy_id]["env_vars"]`
    - If no env_vars provided, store empty dict
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 5.4, 5.5_

  - [x] 2.2 Update `schedule_strategy_route()` (POST `/python/schedule/<strategy_id>`) to accept env_vars
    - Accept optional `env_vars` in JSON body
    - Validate and store if present, leave unchanged if absent
    - Check strategy is not running before allowing modification
    - _Requirements: 3.1, 3.3, 3.6, 2.4_

  - [x] 2.3 Update `api_get_strategy()` (GET `/python/api/strategy/<strategy_id>`) to include env_vars
    - Add `"env_vars": config.get("env_vars", {})` to the response JSON
    - _Requirements: 3.4_

  - [x] 2.4 Implement new env var API endpoints (GET/POST `/python/env/<strategy_id>`)
    - GET: return `{"regular": config.get("env_vars", {}), "secure": {}}`
    - POST: accept `{"regular": {...}, "secure": {}}`, validate regular dict, store in config
    - Verify ownership and check strategy is not running for POST
    - _Requirements: 3.3, 2.4_

  - [ ]* 2.5 Write property test for config storage round-trip (Property 1: Config Storage Round-Trip)
    - **Property 1: Config Storage Round-Trip**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    - Use Hypothesis to generate valid env_vars dicts (non-empty string keys and values), store via validate+save, retrieve via detail API, verify equality

- [x] 3. Checkpoint - Backend routes and utilities
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update subprocess launcher to inject env vars
  - [x] 4.1 Modify `start_strategy_process()` to pass merged environment to `subprocess.Popen`
    - Read `config.get("env_vars", {})` from strategy config
    - Call `build_subprocess_env(strategy_env_vars)` to create merged env
    - Add `subprocess_args["env"] = merged_env`
    - Log injected env var keys (not values) for debugging
    - Handle corrupted env_vars (not a dict) by falling back to empty dict with a warning
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 4.2 Write unit test for subprocess environment injection
    - Test that Popen receives correct merged env with strategy vars overlaid
    - Test fallback when env_vars is missing or corrupted
    - _Requirements: 4.1, 4.4_

- [x] 5. Implement frontend validation utilities and field mapping
  - [x] 5.1 Create `frontend/src/utils/strategy-env-validation.ts`
    - Implement `validateLots(value: string): string | null`
    - Implement `validateTimeFormat(value: string): string | null`
    - Export `STRATEGY_FIELD_MAP` constant mapping field names to env var names
    - Implement `formStateToEnvVars(state)` → filters empty values, returns env_vars dict
    - Implement `envVarsToFormState(envVars)` → returns form state with defaults
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [ ]* 5.2 Write property tests for lots validation (Property 4: Lots Validation)
    - **Property 4: Lots Validation**
    - **Validates: Requirements 5.1**
    - Use fast-check to generate arbitrary strings, verify validateLots returns success iff string is a positive integer ≥ 1

  - [ ]* 5.3 Write property tests for time format validation (Property 5: Time Format Validation)
    - **Property 5: Time Format Validation**
    - **Validates: Requirements 5.2**
    - Use fast-check to generate arbitrary strings, verify validateTimeFormat returns success iff string matches HH:MM with valid hour (00-23) and minute (00-59)

  - [ ]* 5.4 Write property test for field-to-variable mapping (Property 7: Field-to-Variable Name Mapping)
    - **Property 7: Field-to-Variable Name Mapping**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8**
    - Use fast-check to generate form field values, verify formStateToEnvVars produces correct env var names with empty values excluded

- [x] 6. Implement StrategyParametersSection React component
  - [x] 6.1 Create `frontend/src/components/python-strategy/StrategyParametersSection.tsx`
    - Accept props: `values`, `onChange`, `disabled`, `errors`
    - Render fields: Symbol (text), Strike Selection (dropdown), Lots (number min=1), Entry Start Time (time HH:MM), Entry End Time (time HH:MM), Exit Time (time HH:MM), Product (dropdown: MIS/NRML), Exchange (dropdown: NFO/BFO/MCX/CDS)
    - All fields optional with empty defaults
    - Display inline error messages from `errors` prop
    - Disable all fields when `disabled` is true
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.4_

  - [ ]* 6.2 Write unit tests for StrategyParametersSection component
    - Test all fields render with correct labels
    - Test disabled state prevents input
    - Test pre-fill with existing values
    - Test error message display
    - _Requirements: 1.1, 2.1, 2.4_

- [x] 7. Integrate parameters into Create Page
  - [x] 7.1 Update `NewPythonStrategy.tsx` to include StrategyParametersSection
    - Add StrategyParametersSection after the Schedule section
    - Add form state for env vars using `envVarsToFormState({})`
    - Run client-side validation (lots, time fields) on submit
    - Display inline errors on validation failure and prevent submission
    - Convert form state to env_vars dict via `formStateToEnvVars()`
    - Pass env_vars JSON string in FormData via `uploadStrategy` API call
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 5.1, 5.2, 5.3_

- [x] 8. Integrate parameters into Edit Page
  - [x] 8.1 Update `SchedulePythonStrategy.tsx` to include StrategyParametersSection
    - Load existing env_vars from strategy detail API response
    - Pre-fill form state via `envVarsToFormState(strategy.env_vars)`
    - Disable fields when strategy status is "running"
    - On submit, include env_vars in the schedule update request body
    - Run client-side validation before submission
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 9. Update API client to pass env_vars in upload and schedule calls
  - [x] 9.1 Update `uploadStrategy` in `frontend/src/api/python-strategy.ts`
    - Add optional `envVars` parameter to `uploadStrategy` function
    - Append `env_vars` JSON string to FormData when envVars is non-empty
    - _Requirements: 3.2_

  - [x] 9.2 Update `scheduleStrategy` in `frontend/src/api/python-strategy.ts`
    - Add `env_vars` field to the schedule request config type
    - Include env_vars in the POST request body
    - _Requirements: 3.3_

- [x] 10. Checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Final wiring and end-to-end validation
  - [x] 11.1 Verify existing `getEnvVariables`/`saveEnvVariables` API stubs work with new backend endpoints
    - Confirm GET `/python/env/<id>` returns `{regular: {...}, secure: {}}` format
    - Confirm POST `/python/env/<id>` accepts and stores the regular env vars
    - Adjust frontend types or backend response format if needed for compatibility
    - _Requirements: 3.3, 3.4_

  - [ ]* 11.2 Write integration tests for end-to-end flow
    - Test: create strategy with params → verify config stored correctly
    - Test: edit params via schedule API → verify config updated
    - Test: start strategy → verify subprocess env contains strategy vars
    - _Requirements: 3.2, 3.3, 4.1, 4.2_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend is Python (Flask), the frontend is TypeScript (React)
- Existing `getEnvVariables`/`saveEnvVariables` stubs in the API client already point to `/python/env/<id>` — the new backend endpoints must match this contract

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "5.2", "5.3", "5.4", "6.1"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "2.4", "4.1", "6.2"] },
    { "id": 3, "tasks": ["2.5", "4.2", "7.1", "9.1", "9.2"] },
    { "id": 4, "tasks": ["8.1", "11.1"] },
    { "id": 5, "tasks": ["11.2"] }
  ]
}
```
