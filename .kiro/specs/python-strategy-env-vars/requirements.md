# Requirements Document

## Introduction

This feature adds configurable per-strategy environment variables to the Python Strategies system. Currently, strategy scripts can only read global environment variables from the application's `.env` file. This feature introduces a "Strategy Parameters" UI section on both the create and edit pages, allowing users to configure trading parameters (symbol, strike, lots, times, product, exchange) that are stored in the strategy config JSON and passed as environment variables to the subprocess at launch time.

## Glossary

- **Strategy_Parameters_Section**: The UI section on the create and edit pages containing input fields for configurable strategy environment variables
- **Strategy_Config**: The JSON object stored in `strategy_configs.json` representing a single strategy's configuration
- **Env_Vars**: A dictionary of key-value string pairs representing environment variables to pass to the strategy subprocess
- **Subprocess_Launcher**: The `start_strategy_process` function in the backend that spawns the Python subprocess via `subprocess.Popen`
- **Upload_API**: The `/python/new` POST endpoint that accepts a strategy file upload with configuration
- **Schedule_API**: The `/python/schedule/<strategy_id>` POST endpoint that updates a strategy's schedule and parameters
- **Strategy_Detail_API**: The `/python/api/strategy/<strategy_id>` GET endpoint that returns strategy details
- **Create_Page**: The `NewPythonStrategy.tsx` React component for uploading a new strategy
- **Edit_Page**: The `SchedulePythonStrategy.tsx` React component for editing an existing strategy's configuration
- **Parent_Environment**: The set of environment variables inherited from the running Flask application process

## Requirements

### Requirement 1: Strategy Parameters Section on Create Page

**User Story:** As a trader, I want to configure strategy-specific parameters when uploading a new strategy, so that the script receives the correct trading configuration without modifying the global environment.

#### Acceptance Criteria

1. WHEN the Create_Page renders, THE Strategy_Parameters_Section SHALL appear after the Schedule section
2. THE Strategy_Parameters_Section SHALL contain a free-text input field labeled "Symbol" that maps to the `STRATEGY_SYMBOL` environment variable
3. THE Strategy_Parameters_Section SHALL contain a dropdown field labeled "Strike Selection" with values ITM5, ITM4, ITM3, ITM2, ITM1, ATM, OTM1, OTM2, OTM3, OTM4, OTM5 that maps to the `STRATEGY_STRIKE` environment variable
4. THE Strategy_Parameters_Section SHALL contain a numeric input field labeled "Lots" with a minimum value of 1 that maps to the `STRATEGY_LOTS` environment variable
5. THE Strategy_Parameters_Section SHALL contain a time input field labeled "Entry Start Time" in HH:MM format that maps to the `STRATEGY_ENTRY_START` environment variable
6. THE Strategy_Parameters_Section SHALL contain a time input field labeled "Entry End Time" in HH:MM format that maps to the `STRATEGY_ENTRY_END` environment variable
7. THE Strategy_Parameters_Section SHALL contain a time input field labeled "Exit Time" in HH:MM format that maps to the `STRATEGY_EXIT_TIME` environment variable
8. THE Strategy_Parameters_Section SHALL contain a dropdown field labeled "Product" with values MIS and NRML that maps to the `STRATEGY_PRODUCT` environment variable
9. THE Strategy_Parameters_Section SHALL contain a dropdown field labeled "Exchange" with values NFO, BFO, MCX, and CDS that maps to the `STRATEGY_EXCHANGE` environment variable
10. THE Strategy_Parameters_Section SHALL treat all fields as optional with the following defaults: Symbol empty, Strike Selection empty, Lots empty, Entry Start Time empty, Entry End Time empty, Exit Time empty, Product empty, Exchange empty

### Requirement 2: Strategy Parameters Section on Edit Page

**User Story:** As a trader, I want to view and modify strategy parameters on the edit page without re-uploading the script, so that I can adjust trading configuration for an existing strategy.

#### Acceptance Criteria

1. WHEN the Edit_Page loads a strategy with existing Env_Vars, THE Strategy_Parameters_Section SHALL pre-fill each field with the corresponding stored value
2. WHEN the user submits the Edit_Page form, THE Edit_Page SHALL send the updated Env_Vars alongside the schedule configuration to the Schedule_API
3. THE Edit_Page SHALL allow updating Env_Vars independently of re-uploading the strategy script file
4. WHILE a strategy has status "running", THE Edit_Page SHALL prevent modification of the Strategy_Parameters_Section fields

### Requirement 3: Backend Config Storage

**User Story:** As a system operator, I want strategy environment variables persisted in the config JSON, so that parameters survive application restarts and are available when the strategy is launched.

#### Acceptance Criteria

1. THE Strategy_Config SHALL store Env_Vars under a key named `env_vars` as a dictionary of string key-value pairs
2. WHEN the Upload_API receives a request with Env_Vars data, THE Upload_API SHALL persist the Env_Vars in the Strategy_Config for the new strategy
3. WHEN the Schedule_API receives a request with Env_Vars data, THE Schedule_API SHALL update the Env_Vars in the Strategy_Config for the specified strategy
4. WHEN the Strategy_Detail_API returns a strategy, THE Strategy_Detail_API SHALL include the `env_vars` field in the response JSON
5. IF the Upload_API receives a request without Env_Vars data, THEN THE Upload_API SHALL store an empty dictionary as the `env_vars` value
6. THE Strategy_Config SHALL only store Env_Vars entries where the value is a non-empty string

### Requirement 4: Subprocess Environment Variable Injection

**User Story:** As a strategy developer, I want my strategy script to receive the configured parameters as environment variables, so that I can read them with `os.getenv()` without modifying global application state.

#### Acceptance Criteria

1. WHEN the Subprocess_Launcher starts a strategy process, THE Subprocess_Launcher SHALL create a merged environment dictionary containing the Parent_Environment variables combined with the strategy's Env_Vars
2. WHEN the Subprocess_Launcher starts a strategy process, THE Subprocess_Launcher SHALL pass the merged environment dictionary to `subprocess.Popen` via the `env` parameter
3. WHEN a strategy's Env_Vars contain a key that also exists in the Parent_Environment, THE Subprocess_Launcher SHALL use the strategy's Env_Vars value (strategy-level overrides parent-level)
4. IF a strategy has no Env_Vars configured, THEN THE Subprocess_Launcher SHALL pass the Parent_Environment unchanged to the subprocess
5. THE Subprocess_Launcher SHALL convert all Env_Vars values to strings before merging with the Parent_Environment

### Requirement 5: Input Validation

**User Story:** As a trader, I want the system to validate my parameter inputs, so that invalid configurations do not get stored or cause runtime errors.

#### Acceptance Criteria

1. WHEN the user enters a value in the Lots field, THE Create_Page SHALL validate that the value is a positive integer greater than or equal to 1
2. WHEN the user enters a value in a time field (Entry Start, Entry End, Exit Time), THE Create_Page SHALL validate that the value matches HH:MM format
3. IF the user submits the form with an invalid Lots value, THEN THE Create_Page SHALL display an inline error message and prevent submission
4. THE Upload_API SHALL validate that the `env_vars` field, when present, contains only string keys and string values
5. IF the Upload_API receives `env_vars` with non-string keys or values, THEN THE Upload_API SHALL return an error response with status code 400

### Requirement 6: Environment Variable Naming Convention

**User Story:** As a strategy developer, I want consistent and predictable environment variable names, so that I can reliably read strategy parameters in my scripts.

#### Acceptance Criteria

1. THE Strategy_Parameters_Section SHALL map the Symbol field to the environment variable name `STRATEGY_SYMBOL`
2. THE Strategy_Parameters_Section SHALL map the Strike Selection field to the environment variable name `STRATEGY_STRIKE`
3. THE Strategy_Parameters_Section SHALL map the Lots field to the environment variable name `STRATEGY_LOTS`
4. THE Strategy_Parameters_Section SHALL map the Entry Start Time field to the environment variable name `STRATEGY_ENTRY_START`
5. THE Strategy_Parameters_Section SHALL map the Entry End Time field to the environment variable name `STRATEGY_ENTRY_END`
6. THE Strategy_Parameters_Section SHALL map the Exit Time field to the environment variable name `STRATEGY_EXIT_TIME`
7. THE Strategy_Parameters_Section SHALL map the Product field to the environment variable name `STRATEGY_PRODUCT`
8. THE Strategy_Parameters_Section SHALL map the Exchange field to the environment variable name `STRATEGY_EXCHANGE`
