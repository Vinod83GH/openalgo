# Requirements Document

## Introduction

This feature separates the current combined app+broker login flow into two independent stages: a master app login (authenticating the user to OpenAlgo) and a broker login/switch page (authenticating with any supported broker). The broker selection page includes inline credential entry, so the user selects a broker, enters/modifies credentials for that broker, and authenticates — all in one flow. Broker credentials are stored per user per broker in the database, allowing instant broker switching without re-entering credentials.

## Glossary

- **App_Auth**: The master application authentication system that validates user identity against OpenAlgo's user database
- **Broker_Session_Manager**: The subsystem responsible for establishing, tracking, and terminating active broker sessions
- **Broker_Credential_Store**: The database-backed storage for broker API credentials (API key, secret, client ID, redirect URL) keyed by user and broker name, enabling per-user multi-broker credential persistence
- **Active_Broker_Session**: The single currently authenticated broker connection through which all trading operations are routed
- **Broker_Module**: A plugin under `/broker/<name>/api/` that implements broker-specific authentication and trading operations
- **User_Session**: The Flask server-side session representing an authenticated app user, independent of any broker session

## Requirements

### Requirement 1: Standalone App Login

**User Story:** As a user, I want to log in to the OpenAlgo application without being forced to simultaneously authenticate with a broker, so that I can access the app and choose a broker at my own pace.

#### Acceptance Criteria

1. WHEN valid credentials are submitted to the login endpoint, THE App_Auth SHALL authenticate the user and establish a User_Session without initiating any broker authentication
2. WHILE a User_Session is active, THE App_Auth SHALL allow the user to navigate to the broker selection page
3. THE App_Auth SHALL persist the User_Session independently of any Active_Broker_Session
4. WHEN a user logs out of the application, THE App_Auth SHALL terminate both the User_Session and any Active_Broker_Session
5. IF invalid credentials are submitted, THEN THE App_Auth SHALL reject the login attempt and return an error message without affecting any existing session

### Requirement 2: Broker Selection and Login

**User Story:** As a user, I want to select and authenticate with any supported broker after app login, so that I can trade through my preferred broker.

#### Acceptance Criteria

1. WHILE a User_Session is active and no Active_Broker_Session exists, THE Broker_Session_Manager SHALL display a list of configured brokers available for login
2. WHEN the user selects a broker and completes the broker-specific authentication flow, THE Broker_Session_Manager SHALL establish an Active_Broker_Session for that broker
3. THE Broker_Session_Manager SHALL support all broker-specific authentication methods (OAuth callbacks, TOTP, direct token) as defined by each Broker_Module
4. WHEN broker authentication succeeds, THE Broker_Session_Manager SHALL store the auth token and set the active broker in the User_Session
5. IF broker authentication fails, THEN THE Broker_Session_Manager SHALL return the broker-specific error message and keep the user on the broker selection page

### Requirement 3: Single Active Broker Constraint

**User Story:** As a user, I want only one broker to be active at a time, so that all trading operations are routed unambiguously to one broker.

#### Acceptance Criteria

1. THE Broker_Session_Manager SHALL enforce that at most one Active_Broker_Session exists per User_Session at any given time
2. WHEN a user initiates authentication with a new broker while an Active_Broker_Session exists, THE Broker_Session_Manager SHALL terminate the existing Active_Broker_Session before establishing the new one
3. WHEN the existing Active_Broker_Session is terminated during a switch, THE Broker_Session_Manager SHALL revoke the previous broker's auth token from the database
4. WHEN a broker switch completes, THE Broker_Session_Manager SHALL update the session to reflect the newly active broker

### Requirement 4: Broker Logout Without App Logout

**User Story:** As a user, I want to log out of my broker session without being logged out of the app, so that I can switch brokers or remain in the app without re-authenticating.

#### Acceptance Criteria

1. WHEN the user requests broker logout, THE Broker_Session_Manager SHALL terminate the Active_Broker_Session and revoke the broker auth token
2. WHEN broker logout completes, THE Broker_Session_Manager SHALL redirect the user to the broker selection page while preserving the User_Session
3. WHILE no Active_Broker_Session exists, THE Broker_Session_Manager SHALL allow the user to view dashboard pages with empty data and display a prominent warning banner indicating that broker login is required
4. THE App_Auth SHALL remain unaffected by broker logout operations

### Requirement 5: Inline Broker Credential Entry

**User Story:** As an authenticated user, I want to enter or modify broker API credentials directly on the broker selection page and have them stored per broker in the database, so that I can configure credentials once and switch brokers without re-entering them.

#### Acceptance Criteria

1. WHEN the user selects a broker on the broker selection page, THE Broker_Credential_Store SHALL display inline input fields for the required credentials (API key, API secret, client ID, redirect URL) for that broker
2. WHEN the user submits credentials for the selected broker, THE Broker_Credential_Store SHALL persist the credentials in the database keyed by user and broker name
3. THE Broker_Credential_Store SHALL support storing credentials for multiple brokers per user simultaneously
4. WHEN credentials are saved, THE Broker_Credential_Store SHALL immediately proceed to the broker-specific authentication flow using the saved credentials
5. WHEN the user selects a broker with previously stored credentials, THE Broker_Credential_Store SHALL pre-populate the input fields with the existing stored values
6. THE Broker_Credential_Store SHALL encrypt sensitive fields (API secret) before storing them in the database
7. THE Broker_Credential_Store SHALL mask sensitive fields in the API response and input fields when displaying existing values
8. IF the user submits empty or invalid credentials, THEN THE Broker_Credential_Store SHALL display a validation error without initiating broker authentication
9. WHEN broker authentication is initiated, THE Broker_Session_Manager SHALL retrieve credentials from the Broker_Credential_Store for the selected broker and user

### Requirement 6: Trading Feature Compatibility

**User Story:** As a user, I want all existing trading features (orders, positions, kill switch, strategies) to work seamlessly with whichever broker is currently active, so that the multi-broker capability does not break existing functionality.

#### Acceptance Criteria

1. WHILE an Active_Broker_Session exists, THE Broker_Session_Manager SHALL provide the active broker name and auth token to all trading service calls
2. WHEN a trading feature requests broker context, THE Broker_Session_Manager SHALL return credentials for the currently active broker only
3. THE Broker_Session_Manager SHALL use the existing broker-agnostic module architecture (`/broker/<name>/api/`) without modification to the Broker_Module interface
4. IF a trading operation is attempted without an Active_Broker_Session, THEN THE Broker_Session_Manager SHALL return an error indicating that broker login is required

### Requirement 7: Session Status API

**User Story:** As a frontend developer, I want the session status endpoint to report both app authentication state and broker session state, so that the React SPA can render the correct UI.

#### Acceptance Criteria

1. THE App_Auth SHALL return the app authentication status (authenticated or not) in the session status response
2. WHEN an Active_Broker_Session exists, THE App_Auth SHALL include the active broker name in the session status response
3. WHEN no Active_Broker_Session exists but a User_Session is active, THE App_Auth SHALL indicate that the user is authenticated but no broker is connected
4. THE App_Auth SHALL return the list of available brokers (from the Broker_Credential_Store and environment configuration) in the session status response so the frontend can display broker options
