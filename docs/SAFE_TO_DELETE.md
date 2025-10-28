# Safe to Delete - Cleanup Checklist

**Date:** 2025-10-28
**Context:** After Phase 1 refactoring (shared package creation)
**Purpose:** Remove duplicate/obsolete files to improve project clarity

---

## Summary

After the refactoring, these files are now **redundant** or **obsolete**:

| Category | Files | Reason | Can Delete Now? |
|----------|-------|--------|-----------------|
| Duplicate code | 6 files | Moved to shared package | ⚠️ After migration |
| Old fetchers | 4 files | Not used (yfinance/alphavantage) | ✅ Yes |
| Root docs | 3 files | Should be in docs/ | ✅ Yes |
| Duplicate SQL | 1 file | Duplicate of migrations | ✅ Yes |
| Old shared/ | 1 directory | Moved to src/ | ⚠️ After verification |
| Empty tests | 5 directories | Placeholder directories | ⚠️ Keep structure |

**Total Space Saved:** ~50KB of source code + clarity improvement

---

## Category 1: Duplicate Code (Delete After Migration)

### ⚠️ services/data-collector/src/main.py
- **Status:** OLD VERSION (replaced by main_enhanced.py)
- **Action:** Delete after verifying main_enhanced.py works
- **When:** After data-collector migration to shared package
```bash
# When ready:
rm services/data-collector/src/main.py
```

### ⚠️ services/data-collector/src/database.py
- **Status:** OLD VERSION (replaced by database_enhanced.py)
- **Will be replaced by:** `from financial_screener.database import ...`
- **Action:** Delete after migration
- **When:** After data-collector uses shared package
```bash
# When ready:
rm services/data-collector/src/database.py
```

### ⚠️ services/data-collector/src/database_enhanced.py
- **Status:** Current version, but will be replaced by shared package
- **Will be replaced by:** `from financial_screener.database import ...`
- **Action:** Delete after migration complete
- **When:** After data-collector successfully using shared package
```bash
# When ready (after migration tested):
rm services/data-collector/src/database_enhanced.py
```

### ⚠️ services/data-collector/src/main_enhanced.py
- **Status:** Current production version
- **Action:** Rename to main.py after removing old main.py
- **When:** During migration
```bash
# During migration:
rm services/data-collector/src/main.py
mv services/data-collector/src/main_enhanced.py services/data-collector/src/main.py
```

---

## Category 2: Old Fetchers (Delete Now ✅)

### ✅ services/data-collector/src/fetchers/stock_fetcher.py
- **Status:** OLD - Used yfinance (deprecated)
- **Replaced by:** eodhd_fetcher.py
- **Safe to delete:** ✅ Yes
- **Why:** Project migrated from yfinance to EODHD API
```bash
rm services/data-collector/src/fetchers/stock_fetcher.py
```

### ✅ services/data-collector/src/fetchers/alphavantage_fetcher.py
- **Status:** NEVER USED
- **Replaced by:** eodhd_fetcher.py
- **Safe to delete:** ✅ Yes
- **Why:** Decided on EODHD, not Alpha Vantage
```bash
rm services/data-collector/src/fetchers/alphavantage_fetcher.py
```

### ✅ services/data-collector/src/fetchers/bond_fetcher.py
- **Status:** STUB (empty placeholder)
- **Safe to delete:** ✅ Yes
- **Why:** Bonds not yet implemented (Phase 6+)
- **Note:** Will recreate when needed
```bash
rm services/data-collector/src/fetchers/bond_fetcher.py
```

### ✅ services/data-collector/src/fetchers/etf_fetcher.py
- **Status:** STUB (empty placeholder)
- **Safe to delete:** ✅ Yes
- **Why:** ETFs handled by eodhd_fetcher.py
```bash
rm services/data-collector/src/fetchers/etf_fetcher.py
```

---

## Category 3: Root-Level Docs (Move to docs/ ✅)

### ✅ CLEANUP_RECOMMENDATIONS.md
- **Status:** OLD (from previous cleanup attempt)
- **Action:** Move to docs/archive/
```bash
mv CLEANUP_RECOMMENDATIONS.md docs/archive/
```

### ✅ DEPLOYMENT_SUCCESS.md
- **Status:** ONE-TIME deployment log
- **Action:** Move to docs/archive/
```bash
mv DEPLOYMENT_SUCCESS.md docs/archive/
```

### ✅ SCHEMA_DESIGN.md
- **Status:** Outdated schema documentation
- **Action:** Move to docs/architecture/
- **Note:** May need updating to reflect current schema
```bash
mv SCHEMA_DESIGN.md docs/architecture/
```

---

## Category 4: Duplicate SQL (Delete Now ✅)

### ✅ database/init-schema.sql
- **Status:** DUPLICATE of migrations/001-005
- **Safe to delete:** ✅ Yes
- **Why:** Migration files (001-007) are the source of truth
```bash
rm database/init-schema.sql
```

---

## Category 5: Old shared/ Directory (After Verification ⚠️)

### ⚠️ shared/
- **Status:** Content moved to src/financial_screener/
- **Safe to delete:** ⚠️ After verification
- **When:** After confirming all services use src/financial_screener/
```bash
# Check what's still there:
ls -la shared/

# When ready (after verification):
rm -rf shared/
```

**Before deleting, verify:**
```bash
# Check if anything imports from shared/
grep -r "from shared" services/ airflow/ 2>/dev/null
grep -r "import shared" services/ airflow/ 2>/dev/null

# If no results, safe to delete
```

---

## Category 6: Empty Test Directories (Keep Structure ✅)

These are **empty placeholder directories** - keep them for structure:

- `services/api/tests/` - Keep for Phase 4
- `services/sentiment-engine/tests/` - Keep for Phase 6
- `services/news-fetcher/tests/` - Keep for Phase 6
- `services/data-collector/tests/` - Keep (add tests soon!)
- `airflow/tests/` - Keep (add tests soon!)

**Action:** ✅ **Keep directories** - Add .gitkeep files
```bash
touch services/api/tests/.gitkeep
touch services/sentiment-engine/tests/.gitkeep
touch services/news-fetcher/tests/.gitkeep
touch services/data-collector/tests/.gitkeep
touch airflow/tests/.gitkeep
```

---

## Safe Cleanup Script (Immediate Actions)

```bash
#!/bin/bash
# Safe cleanup script - deletes only 100% safe files

cd /root/gitlab/financial-screener

echo "=== PHASE 1: Safe Immediate Cleanup ==="

# 1. Delete old fetchers (not used)
echo "Deleting old fetchers..."
rm -f services/data-collector/src/fetchers/stock_fetcher.py
rm -f services/data-collector/src/fetchers/alphavantage_fetcher.py
rm -f services/data-collector/src/fetchers/bond_fetcher.py
rm -f services/data-collector/src/fetchers/etf_fetcher.py

# 2. Delete duplicate SQL
echo "Deleting duplicate SQL..."
rm -f database/init-schema.sql

# 3. Move root docs to archive
echo "Archiving old docs..."
mkdir -p docs/archive docs/architecture
mv CLEANUP_RECOMMENDATIONS.md docs/archive/ 2>/dev/null || true
mv DEPLOYMENT_SUCCESS.md docs/archive/ 2>/dev/null || true
mv SCHEMA_DESIGN.md docs/architecture/ 2>/dev/null || true

# 4. Add .gitkeep to empty test directories
echo "Adding .gitkeep to test directories..."
touch services/api/tests/.gitkeep
touch services/sentiment-engine/tests/.gitkeep
touch services/news-fetcher/tests/.gitkeep
touch services/data-collector/tests/.gitkeep
touch airflow/tests/.gitkeep

echo "✓ Safe cleanup complete"
echo ""
echo "=== PHASE 2: Post-Migration Cleanup (run after migration) ==="
echo "# After data-collector migration:"
echo "rm services/data-collector/src/main.py"
echo "rm services/data-collector/src/database.py"
echo "rm services/data-collector/src/database_enhanced.py"
echo "mv services/data-collector/src/main_enhanced.py services/data-collector/src/main.py"
echo ""
echo "# After verifying no imports from shared/:"
echo "rm -rf shared/"
```

---

## Post-Migration Cleanup Script (Run Later)

```bash
#!/bin/bash
# Run AFTER data-collector migrated to shared package

cd /root/gitlab/financial-screener

echo "=== Post-Migration Cleanup ==="

# Verify no imports from old locations
echo "Checking for old imports..."
if grep -r "from database import\|from config import" services/data-collector/src/ 2>/dev/null; then
    echo "❌ ERROR: Found old imports. Migration not complete."
    exit 1
fi

# Verify shared package imports work
echo "Verifying shared package imports..."
if ! grep -r "from financial_screener" services/data-collector/src/ 2>/dev/null; then
    echo "❌ ERROR: No shared package imports found. Migration not complete."
    exit 1
fi

echo "✓ Verification passed"

# Delete old files
echo "Deleting old data-collector files..."
rm -f services/data-collector/src/main.py
rm -f services/data-collector/src/database.py
rm -f services/data-collector/src/database_enhanced.py

# Rename main_enhanced to main
if [ -f services/data-collector/src/main_enhanced.py ]; then
    mv services/data-collector/src/main_enhanced.py services/data-collector/src/main.py
    echo "✓ Renamed main_enhanced.py to main.py"
fi

# Check if safe to delete shared/
echo "Checking shared/ directory usage..."
if grep -r "from shared\|import shared" . --exclude-dir=.git 2>/dev/null; then
    echo "⚠️  WARNING: Found imports from shared/ - NOT deleting"
else
    echo "Deleting shared/ directory..."
    rm -rf shared/
    echo "✓ shared/ deleted"
fi

echo "✓ Post-migration cleanup complete"
```

---

## Size Savings

| Category | Files | Size | Impact |
|----------|-------|------|--------|
| Old fetchers | 4 files | ~15 KB | Clarity |
| Duplicate SQL | 1 file | ~10 KB | Clarity |
| Old docs | 3 files | ~25 KB | Organization |
| After migration | 6 files | ~40 KB | Eliminates duplication |
| **Total** | **14 files** | **~90 KB** | **Much clearer project** |

---

## Before You Delete Checklist

### Immediate Cleanup (Safe Now)
- [x] Verify old fetchers not imported anywhere
- [x] Confirm database/init-schema.sql is duplicate
- [x] Check root docs are redundant
- [ ] Run safe cleanup script

### Post-Migration Cleanup (After data-collector migration)
- [ ] Verify data-collector uses shared package
- [ ] Test data-collector in Docker
- [ ] Deploy to cluster successfully
- [ ] Confirm no imports from old locations
- [ ] Run post-migration cleanup script

---

## Rollback Plan

If cleanup causes issues:

### Immediate Cleanup Rollback:
```bash
# Restore from git
git checkout services/data-collector/src/fetchers/
git checkout database/init-schema.sql
git checkout CLEANUP_RECOMMENDATIONS.md
git checkout DEPLOYMENT_SUCCESS.md
git checkout SCHEMA_DESIGN.md
```

### Post-Migration Rollback:
```bash
# If migration fails, revert Docker image
docker tag financial-data-collector:pre-refactor financial-data-collector:latest

# Redeploy old version
kubectl delete pods -n financial-screener -l app=data-collector
```

---

## Summary

**Can Delete Now (Safe):**
- ✅ 4 old fetchers
- ✅ 1 duplicate SQL file
- ✅ 3 root-level docs (move to docs/)

**Delete After Migration:**
- ⚠️ Old main.py, database.py, database_enhanced.py
- ⚠️ shared/ directory

**Keep:**
- ✅ Empty test directories (add .gitkeep)
- ✅ All STATUS.md files
- ✅ All documentation in docs/

**Total Impact:** Removes ~14 redundant files, saves ~90KB, significantly improves project clarity

---

## Recommended Action

**Option 1: Conservative (Recommended)**
```bash
# Run only immediate safe cleanup
./docs/cleanup_scripts/safe_cleanup.sh
# Total: Delete 8 files
```

**Option 2: Aggressive (After Migration)**
```bash
# Run immediate + post-migration cleanup
./docs/cleanup_scripts/safe_cleanup.sh
# After successful migration:
./docs/cleanup_scripts/post_migration_cleanup.sh
# Total: Delete 14 files + shared/ directory
```

**Last Updated:** 2025-10-28
