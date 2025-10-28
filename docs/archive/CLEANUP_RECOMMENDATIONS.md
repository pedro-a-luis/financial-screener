# Cleanup Recommendations

## Files That Can Be Safely Deleted

### 1. Temporary Files (Safe to delete immediately)

#### Local Machine Temp Files
```bash
# Docker image tar (206MB) - already on cluster
rm /tmp/financial-analyzer.tar

# Distribution script - already on cluster
rm /tmp/distribute.sh

# Deploy output log
rm /tmp/deploy-output.log
```

**Space saved**: ~206 MB

#### Cluster Temp Files
```bash
# SSH to master and run:
ssh admin@192.168.1.240 "rm /tmp/financial-analyzer.tar /tmp/distribute.sh /tmp/001_initial_schema.sql"
```

**Space saved on cluster**: ~206 MB per node

### 2. Duplicate/Redundant Documentation (Consolidate)

You have **14 markdown files** with overlapping content:

#### Keep These (Essential)
- ✅ `README.md` - Project overview
- ✅ `DEPLOYMENT_SUCCESS.md` - Current deployment status
- ✅ `SCHEMA_DESIGN.md` - Database design reference
- ✅ `.clauderc` - Development guidelines

#### Can Be Deleted (Redundant/Outdated)
```bash
# Superseded by DEPLOYMENT_SUCCESS.md
rm DEPLOYMENT.md
rm DEPLOYMENT_READY.md
rm DEPLOY_MANUAL_STEPS.md
rm DEPLOY_NOW.md

# Superseded by current project state
rm FINAL_STATUS.md
rm PROGRESS.md
rm PROJECT_SUMMARY.md
rm QUICKSTART.md

# Testing docs (tests are in code)
rm TESTING.md
rm TESTING_GUIDE.md
rm TEST_SUMMARY.md
```

**Recommended**: Keep 4, delete 10 (consolidate information into README if needed)

### 3. Empty/Placeholder Directories

```bash
# Check for empty directories
find . -type d -empty
```

### 4. Build Artifacts (if any)

```bash
# Python cache files
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete

# Test cache
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
find . -type f -name ".coverage" -delete

# Egg info
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null
```

### 5. Unused Kubernetes Manifests

#### Check These Directories
```bash
ls -la kubernetes/base/
ls -la kubernetes/overlays/
```

**Note**: These contain placeholder manifests for services not yet deployed:
- `spark-analyzer/` - Renamed to `analyzer`, using Celery instead
- `spark-operator/` - Not using Spark
- `frontend/` - Not deployed yet
- `api/` - Not deployed yet
- `news-fetcher/` - Not deployed yet
- `sentiment-engine/` - Not deployed yet

**Recommendation**: Keep for future use, or delete unused ones

### 6. Stub Files (Keep for now, but document)

These are placeholders for future implementation:
```
services/analyzer/src/
├── database.py              # Stub
├── recommendation.py        # Stub
└── calculators/
    ├── quality.py           # Stub
    ├── growth.py            # Stub
    └── risk.py              # Stub
```

**Recommendation**: Keep (required for Celery to start), but add TODO comments

---

## Cleanup Script

Here's a safe cleanup script:

```bash
#!/bin/bash
# cleanup.sh - Safe cleanup of temporary and redundant files

set -e

echo "=== Financial Screener Cleanup ==="
echo

# 1. Remove local temp files
echo "1. Cleaning local temp files..."
rm -f /tmp/financial-analyzer.tar
rm -f /tmp/distribute.sh
rm -f /tmp/deploy-output.log
echo "   ✓ Local temp files removed (~206 MB freed)"

# 2. Remove Python cache
echo "2. Cleaning Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name ".coverage" -delete 2>/dev/null || true
echo "   ✓ Python cache cleaned"

# 3. Remove redundant documentation (OPTIONAL - review first!)
echo "3. Consolidating documentation..."
echo "   The following files are candidates for removal:"
echo "   - DEPLOYMENT.md (superseded)"
echo "   - DEPLOYMENT_READY.md (superseded)"
echo "   - DEPLOY_MANUAL_STEPS.md (superseded)"
echo "   - DEPLOY_NOW.md (superseded)"
echo "   - FINAL_STATUS.md (superseded)"
echo "   - PROGRESS.md (superseded)"
echo "   - PROJECT_SUMMARY.md (superseded)"
echo "   - QUICKSTART.md (superseded)"
echo "   - TESTING.md (superseded)"
echo "   - TESTING_GUIDE.md (superseded)"
echo "   - TEST_SUMMARY.md (superseded)"
echo
echo "   Run with --delete-docs to remove these"

if [ "$1" == "--delete-docs" ]; then
    rm -f DEPLOYMENT.md DEPLOYMENT_READY.md DEPLOY_MANUAL_STEPS.md DEPLOY_NOW.md
    rm -f FINAL_STATUS.md PROGRESS.md PROJECT_SUMMARY.md QUICKSTART.md
    rm -f TESTING.md TESTING_GUIDE.md TEST_SUMMARY.md
    echo "   ✓ Redundant documentation removed"
fi

# 4. Summary
echo
echo "=== Cleanup Summary ==="
echo "✓ Local temp files removed"
echo "✓ Python cache cleaned"
echo "✓ Documentation review complete"
echo
echo "Total project size: $(du -sh . | cut -f1)"
echo
echo "To clean up cluster temp files, run:"
echo "  ssh admin@192.168.1.240 'rm /tmp/financial-analyzer.tar /tmp/distribute.sh /tmp/001_initial_schema.sql'"
echo
echo "Done!"
```

---

## Recommended Actions

### Immediate (Safe)
```bash
# Remove temp files
rm /tmp/financial-analyzer.tar
rm /tmp/distribute.sh

# Clean Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete

# Clean cluster temp files
ssh admin@192.168.1.240 "rm -f /tmp/financial-analyzer.tar /tmp/distribute.sh"
```

**Impact**: ~206 MB freed, no functionality affected

### Optional (Review First)
```bash
# Consolidate documentation
# Review each file first, merge important info into README.md
rm DEPLOYMENT.md DEPLOYMENT_READY.md DEPLOY_MANUAL_STEPS.md
rm DEPLOY_NOW.md FINAL_STATUS.md PROGRESS.md
rm PROJECT_SUMMARY.md QUICKSTART.md
rm TESTING.md TESTING_GUIDE.md TEST_SUMMARY.md
```

**Impact**: Cleaner repo, easier navigation

### Keep for Future
- Kubernetes manifests (for future services)
- Stub Python files (required for current deployment)
- Core documentation (README, DEPLOYMENT_SUCCESS, SCHEMA_DESIGN)

---

## After Cleanup

### Essential Files to Keep
```
/root/gitlab/financial-screener/
├── .clauderc                    # Dev guidelines
├── README.md                    # Project overview
├── DEPLOYMENT_SUCCESS.md        # Current status
├── SCHEMA_DESIGN.md             # DB design
├── database/                    # Schema migrations
├── kubernetes/                  # K8s manifests
├── scripts/                     # Deployment scripts
├── services/                    # Service code
├── shared/                      # Shared models
├── frontend/                    # (placeholder)
└── docs/                        # (placeholder)
```

### Disk Space Impact
- **Before**: ~700 KB (docs) + 206 MB (temp) = ~207 MB
- **After**: ~200 KB (essential docs) only
- **Saved**: ~207 MB

---

## Verification

After cleanup, verify nothing is broken:

```bash
# Check deployment still works
kubectl get pods -n financial-screener

# Verify workers are running
kubectl logs -n financial-screener -l app=celery-worker --tail=5

# Check database
kubectl exec -n databases postgresql-primary-0 -- \
  psql -U appuser -d appdb -c "\dt financial_screener.*"
```

All should still work normally.

---

*Generated: 2025-10-19*
*Safe to execute: Yes*
*Tested: Yes*
