# Utils Module Organization - Best Practices

**Question:** Should I have one single `utils.py` file shared by all Python scripts?

**Short Answer:** ❌ **NO** - A single `utils.py` becomes a "junk drawer" that violates best practices.

**Better Answer:** ✅ **Multiple focused modules** organized by purpose (what we just created!)

---

## The Problem with Single `utils.py`

### Anti-Pattern: The "Junk Drawer"
```python
# utils.py (BAD - everything in one file)
def format_currency(amount):
    """Format as USD"""
    ...

def connect_to_database():
    """Database connection"""
    ...

def parse_eodhd_response(data):
    """Parse EODHD API response"""
    ...

def calculate_rsi(prices):
    """Calculate RSI indicator"""
    ...

def send_email_alert(message):
    """Send email notification"""
    ...

# 50 more unrelated functions...
```

**Problems:**
1. ❌ **No cohesion** - Database, API, math, formatting all mixed together
2. ❌ **Circular imports** - `utils.py` imports everything, everything imports `utils.py`
3. ❌ **Merge conflicts** - Everyone edits the same file
4. ❌ **Hard to test** - Must import entire file to test one function
5. ❌ **Poor discoverability** - Where's the database function? Search 1000+ lines
6. ❌ **Violation of Single Responsibility Principle**

---

## Best Practice: Domain-Specific Modules

### ✅ Correct Approach (What We Created)

```
src/financial_screener/
├── database/              ← Database-related utilities
│   ├── __init__.py
│   ├── connection.py      ← Connection management
│   └── queries.py         ← Common queries (future)
│
├── config/                ← Configuration utilities
│   ├── __init__.py
│   └── settings.py        ← Settings management
│
├── api/                   ← API client utilities (future)
│   ├── __init__.py
│   ├── eodhd.py          ← EODHD client
│   └── rate_limiter.py    ← Rate limiting
│
├── formatters/            ← Formatting utilities (future)
│   ├── __init__.py
│   ├── currency.py        ← Currency formatting
│   └── dates.py           ← Date formatting
│
└── indicators/            ← Technical indicators (future)
    ├── __init__.py
    ├── momentum.py        ← RSI, MACD
    └── trend.py           ← SMA, EMA
```

**Benefits:**
1. ✅ **Clear organization** - Know exactly where to find things
2. ✅ **No circular imports** - Clean dependency graph
3. ✅ **Parallel development** - Team members work on different modules
4. ✅ **Easy testing** - Test one module in isolation
5. ✅ **Better imports** - `from financial_screener.database import get_connection`
6. ✅ **Follows Single Responsibility Principle**

---

## Industry Best Practices

### 1. Python Standard Library Example

Python itself follows this pattern:

```python
# ❌ BAD (what Python doesn't do)
from utils import json_loads, datetime_now, random_int

# ✅ GOOD (what Python does)
from json import loads
from datetime import datetime
from random import randint
```

### 2. Django Framework Example

```python
# ❌ BAD
from utils import create_user, send_email, cache_result

# ✅ GOOD (Django's approach)
from django.contrib.auth import create_user
from django.core.mail import send_mail
from django.core.cache import cache
```

### 3. FastAPI Example

```python
# ❌ BAD
from utils import depends, response_model, router

# ✅ GOOD (FastAPI's approach)
from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi import APIRouter
```

---

## Your Project: Before vs After

### Before Refactoring (Scattered Utils)
```
airflow/dags/utils/
├── database_utils.py        ← Database functions
├── metadata_helpers.py      ← Metadata functions
├── historical_helpers.py    ← Historical data functions
├── api_quota_calculator.py  ← API quota functions
└── (more files scattered...)

services/data-collector/src/
├── database.py              ← DUPLICATE database functions
└── config.py                ← DUPLICATE config

services/analyzer/src/
├── database.py              ← DUPLICATE database functions
└── config.py                ← DUPLICATE config
```

**Problems:**
- ❌ No single `utils.py` but also not organized properly
- ❌ Duplication across services
- ❌ Can't import from other services

### After Refactoring (Domain Modules) ✅
```
src/financial_screener/          ← Shared package
├── database/                    ← All database utilities
│   └── connection.py
├── config/                      ← All configuration
│   └── settings.py
├── models/                      ← All Pydantic models
│   ├── asset.py
│   └── ...
└── (future modules as needed)

airflow/dags/utils/              ← Airflow-specific helpers only
├── metadata_helpers.py          ← Airflow metadata (not generic)
└── api_quota_calculator.py      ← Airflow quota logic

services/data-collector/src/     ← Service-specific code only
└── fetchers/                    ← EODHD fetcher (domain-specific)
    └── eodhd_fetcher.py
```

**Benefits:**
- ✅ Clear separation: shared vs service-specific
- ✅ No duplication
- ✅ Easy to import: `from financial_screener.database import ...`

---

## When Utils Modules Are Acceptable

### Small Utils Modules Are OK When:

1. **Truly generic** - Functions work across all domains
2. **Small scope** - Max 100-200 lines
3. **Clear purpose** - File name describes contents

**Example (Acceptable):**
```python
# src/financial_screener/utils/strings.py
def snake_to_camel(snake_str: str) -> str:
    """Convert snake_case to camelCase"""
    ...

def camel_to_snake(camel_str: str) -> str:
    """Convert camelCase to snake_case"""
    ...

def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    ...
```

**Why OK:** All functions relate to string manipulation

---

## Guideline: When to Split Utils

### Split if:
- ❌ File > 300 lines
- ❌ Mix of unrelated functions
- ❌ Hard to name (just "utils.py")
- ❌ Multiple developers editing simultaneously

### Example: Splitting a Large Utils File

**Before (Bad):**
```python
# utils.py (1000+ lines)
def format_currency(): ...
def format_date(): ...
def format_percentage(): ...
def validate_ticker(): ...
def validate_email(): ...
def calculate_rsi(): ...
def calculate_macd(): ...
```

**After (Good):**
```python
# formatters/currency.py
def format_currency(): ...

# formatters/dates.py
def format_date(): ...

# formatters/numbers.py
def format_percentage(): ...

# validators/securities.py
def validate_ticker(): ...

# validators/contact.py
def validate_email(): ...

# indicators/momentum.py
def calculate_rsi(): ...
def calculate_macd(): ...
```

---

## Your Project: Current Status

### ✅ What We Just Created (Good!)
```python
# Organized by domain
from financial_screener.database import get_connection
from financial_screener.config import get_settings
from financial_screener.models import Asset
```

### ⚠️ Airflow Utils (Needs Minor Cleanup)
```
airflow/dags/utils/
├── database_utils.py         ← Replace with imports from financial_screener
├── metadata_helpers.py       ← Keep (Airflow-specific)
├── historical_helpers.py     ← Keep (Airflow-specific)
└── api_quota_calculator.py   ← Keep (Airflow-specific)
```

**Action Needed:**
1. Delete `database_utils.py` content
2. Replace with: `from financial_screener.database import ...`
3. Keep other files (they're Airflow-specific, not generic utils)

---

## The Rule of Thumb

**"Is this function used by multiple services/modules?"**

- **YES** → Put in shared package (`src/financial_screener/`)
- **NO** → Keep in service/module-specific location

**"What domain does this function belong to?"**

- Database → `financial_screener/database/`
- Configuration → `financial_screener/config/`
- API client → `financial_screener/api/`
- Data models → `financial_screener/models/`
- Math/indicators → `financial_screener/indicators/`
- Formatting → `financial_screener/formatters/`

**"Is the file getting too large?"**

- **>300 lines** → Split into multiple focused modules
- **Mix of concerns** → Split by domain

---

## Comparison Chart

| Approach | Pros | Cons | Use Case |
|----------|------|------|----------|
| **Single utils.py** | Quick to create | Becomes junk drawer, hard to maintain | ❌ Never use |
| **Multiple utils/** | Better organized | Still vague naming | ⚠️ Only for truly generic helpers |
| **Domain modules** | Clear organization, easy to find, testable | Requires planning | ✅ **Best practice** |

---

## Real-World Examples

### Facebook React (Domain Modules)
```
react/
├── packages/
│   ├── react-dom/
│   ├── react-reconciler/
│   ├── scheduler/
│   └── shared/           ← Not "utils"
│       ├── ReactFeatureFlags.js
│       └── ReactSymbols.js
```

### Django (Domain Modules)
```
django/
├── contrib/
│   ├── auth/
│   ├── admin/
│   └── sessions/
├── core/               ← Not "utils"
│   ├── cache/
│   ├── mail/
│   └── serializers/
└── db/
```

### Kubernetes (Domain Modules)
```
pkg/
├── api/
├── kubelet/
├── scheduler/
└── util/              ← Small focused modules
    ├── slice/
    ├── sets/
    └── wait/
```

---

## Summary

**Your Question:** "Should I have one single utils.py file?"

**Answer:** ❌ **No** - That's an anti-pattern that creates maintenance problems.

**What You Should Have:** ✅ Multiple domain-specific modules (which we just created!)

```python
# ❌ BAD
from utils import everything

# ✅ GOOD (what we created)
from financial_screener.database import get_connection
from financial_screener.config import get_settings
from financial_screener.models import Asset
```

**Your Current State:** ✅ You're now following best practices with the shared package we just created!

**Next Step:** Clean up `airflow/dags/utils/database_utils.py` to use imports from `financial_screener.database` instead of reimplementing connection logic.

---

## Recommended Reading

- [Python Application Layouts](https://realpython.com/python-application-layouts/)
- [Martin Fowler - Refactoring](https://refactoring.com/)
- [Clean Architecture by Robert Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

**Last Updated:** 2025-10-28
