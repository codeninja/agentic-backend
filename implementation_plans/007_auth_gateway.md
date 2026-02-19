# Implementation Plan 007: Ninja Auth Gateway (`libs/ninja-auth`)

> **Milestone**: 5 — Auth Gateway
> **Tickets**: 5.1, 5.2, 5.3

## Objective
Build a pluggable authentication and identity gateway that secures all agentic routes. The gateway authenticates requests, resolves user identity, and injects user context into the agent orchestration layer so agents know *who* they're acting for.

## Requirements
- **Strategy pattern**: Pluggable auth modules — swap between OAuth2, JWT, API keys, or custom providers.
- **User registration**: Built-in identity module for email/password signup, login, session management.
- **External providers**: First-class support for Google OAuth, GitHub OAuth, Auth0, and Okta.
- **Context injection**: Authenticated user identity is available to every agent in the request chain.
- **RBAC foundation**: Role-based access control at the domain/entity level (e.g., "this user can read Orders but not Billing").
- **Configurable via ASD**: Auth requirements are declarable in `.ninjastack/auth.json`.

## Auth Strategy Modules
| Strategy | Description |
|----------|-------------|
| `OAuth2Strategy` | Google, GitHub, custom OAuth2 providers |
| `BearerStrategy` | JWT validation (Auth0, Okta, self-issued) |
| `ApiKeyStrategy` | Simple API key auth for service-to-service |
| `IdentityStrategy` | Built-in user registration, login, password reset |

## Architecture
```
Request ──→ Ninja Auth Gateway (middleware)
               │
               ├─ Resolve Strategy (OAuth2? JWT? API Key?)
               ├─ Validate Credentials
               ├─ Load User Context (roles, permissions)
               │
               └──→ Inject into Agent Request Context
                         │
                    Coordinator Agent (knows who the user is)
```

## File Structure
```
libs/ninja-auth/
├── pyproject.toml
├── src/ninja_auth/
│   ├── __init__.py
│   ├── gateway.py            # FastAPI middleware / dependency
│   ├── context.py            # User context model injected into agents
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── oauth2.py
│   │   ├── bearer.py
│   │   ├── apikey.py
│   │   └── identity.py       # Registration, login, sessions
│   ├── rbac.py               # Role-based access control
│   └── config.py             # Read from .ninjastack/auth.json
└── tests/
```

## Acceptance Criteria
- [ ] OAuth2 flow works end-to-end with Google as provider.
- [ ] JWT bearer tokens from Auth0 are validated and user context is extracted.
- [ ] Built-in identity module supports registration, login, and session management.
- [ ] Authenticated user context is accessible inside ADK agent tool execution.
- [ ] RBAC rules prevent unauthorized domain access.

## Dependencies
- Plan 002 (ASD Core Models — for domain/entity permission declarations)
- Plan 004 (Unified Persistence — for storing user/session data)
