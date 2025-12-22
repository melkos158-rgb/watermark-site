# Debug Logging & Traceback Setup for Proofly

## Level 1: Readable Tracebacks

### rich
```
pip install rich
```
Add to app.py (top):
```python
from rich.traceback import install
install(show_locals=True)
```

### better-exceptions (optional, local)
```
pip install better-exceptions
```
Add to app.py (top, after imports):
```python
import better_exceptions
better_exceptions.hook()
```

## Level 2: Structured Logging

### structlog
```
pip install structlog
```
Minimal setup in app.py:
```python
import structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
log = structlog.get_logger()
```
Usage example:
```python
log.error(
    "favorite_toggle_failed",
    user_id=current_user.id if current_user.is_authenticated else None,
    item_id=item_id,
    reason="not_authenticated"
)
```

## Level 3: Runtime Error Tracking

### sentry-sdk
```
pip install sentry-sdk
```
Add to app.py:
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0,
)
```

## Level 4: Static Analysis

### ruff
```
pip install ruff
ruff check .
```

### mypy
```
pip install mypy
```
Add type hints to functions for better Copilot suggestions.

## Level 5: System-wide Context

### pytest + pytest-cov
```
pip install pytest pytest-cov
```

### watchdog (for auto-reload logs)

## Level 6: Copilot Debug Context

See DEBUG_CONTEXT.md for common issues and environment info.
