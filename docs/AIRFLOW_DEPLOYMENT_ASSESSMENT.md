# Airflow Deployment Assessment
**Date:** 2025-10-29
**Airflow Version:** 3.0.2 (Helm Chart 1.18.0)
**Cluster:** 7-node Raspberry Pi cluster

---

## Executive Summary

### Overall Status: ⚠️ **PARTIALLY OPERATIONAL**

| Component | Status | Details |
|-----------|--------|---------|
| **API Server (UI)** | ✅ Running | Accessible at airflow.stratdata.org:8080 |
| **PostgreSQL** | ✅ Running | Metadata database operational |
| **DAG Processor** | ⚠️ Partial | 1 pod running, 1 pod stuck (PVC conflict) |
| **Scheduler** | ❌ Failed | Stuck in Init (PVC conflict) |
| **Triggerer** | ✅ Running | Operational |
| **DAGs Visibility** | ❌ Not Visible | No DAGs in database or UI |

**Critical Issues:** 2
**Warnings:** 3
**Recommendations:** 5

---

## 1. Pod Status Analysis

### Running Pods (3/7)

1. **airflow-api-server-76b4497c84-wh26j**
   - Status: Running (1/1)
   - Node: pi-worker-04
   - Age: 86 minutes
   - Purpose: Serves Airflow UI and REST API
   - **Assessment:** ✅ Healthy

2. **airflow-dag-processor-77d874dd68-gmggw**
   - Status: Running (2/2)
   - Node: pi-master
   - Age: 12 minutes
   - Purpose: Parses and serializes DAG files
   - **Assessment:** ⚠️ Running but DAG files missing

3. **airflow-triggerer-0**
   - Status: Running (2/2)
   - Node: pi-worker-07
   - Age: 16 minutes
   - Purpose: Handles deferrable operators
   - **Assessment:** ✅ Healthy

4. **airflow-postgresql-0**
   - Status: Running (1/1)
   - Node: pi-worker-05
   - Age: 31 minutes
   - Purpose: Airflow metadata database
   - **Assessment:** ✅ Healthy

5. **airflow-statsd-75fdf4bc64-4q4nr**
   - Status: Running (1/1)
   - Node: pi-master
   - Age: 8 days
   - Purpose: Metrics collection
   - **Assessment:** ✅ Healthy

### Failed/Stuck Pods (2/7)

1. **airflow-scheduler-0** ❌
   - Status: Init:0/1 (Stuck)
   - Node: Assigned to pi-worker-06, not starting
   - Age: 16 minutes
   - **Issue:** PVC attachment conflict
   - **Impact:** No DAG scheduling, DAGs cannot execute
   - **Severity:** CRITICAL

2. **airflow-dag-processor-d55949988-69nzr** ❌
   - Status: Init:0/1 (Stuck)
   - Node: Assigned to pi-worker-03, not starting
   - Age: 16 minutes
   - **Issue:** Multi-Attach error for PVC pvc-d0aad7bd-81df-4579-8747-1e7581c8b804
   - **Error:** "Volume is already used by pod(s) airflow-triggerer-0"
   - **Impact:** Redundant DAG processor not available
   - **Severity:** HIGH

---

## 2. Critical Issues

### Issue #1: PVC Multi-Attach Conflict ❌ CRITICAL

**Problem:**
The `airflow-dags` PVC (RWO - ReadWriteOnce) is being claimed by multiple pods simultaneously:
- `airflow-triggerer-0` has it mounted
- `airflow-dag-processor-d55949988-69nzr` cannot attach (blocked)
- `airflow-scheduler-0` likely also blocked

**Root Cause:**
- Helm upgrade enabled `dags.persistence.enabled=true`
- Chart attempts to mount same PVC to multiple pods
- Longhorn RWO volumes can only attach to ONE node at a time
- Triggerer should NOT need DAG PVC but Helm chart is mounting it

**Impact:**
- Scheduler cannot start → No DAG execution
- Redundant DAG processor blocked
- System partially functional (only 1 DAG processor working)

**Resolution Required:**
Change PVC access mode to ReadWriteMany (RWX) OR disable DAG persistence and use alternative method (git-sync, custom image, ConfigMap)

### Issue #2: DAGs Not Visible in UI ❌ CRITICAL

**Problem:**
No DAGs visible in Airflow UI or database

**Evidence:**
```sql
SELECT dag_id FROM serialized_dag;
-- Result: 0 rows
```

**Root Cause:**
1. DAG files copied to `/opt/airflow/dags/` in pod `gmggw`
2. Files verified present after copy
3. Pod restarted → Files lost (PVC not actually persisting)
4. DAG processor finding 0 files during scan
5. No serialization happening

**Impact:**
- Users cannot see or trigger DAGs
- `historical_load_equities` cannot be tested
- System not functional for workflows

**Resolution Required:**
Implement proper DAG deployment strategy (recommendation below)

---

## 3. Configuration Issues

### Helm Configuration

**Current Values:**
```yaml
dags:
  persistence:
    enabled: true      # ❌ Causing PVC conflicts
    size: 1Gi
    storageClassName: longhorn
    accessMode: RWO    # ❌ Should be RWX for multi-pod access

executor: LocalExecutor  # ✅ Appropriate for cluster size

postgresql:
  enabled: true        # ✅ Embedded PostgreSQL

webserver:
  enabled: true        # ✅ Now enabled
  defaultUser:
    username: admin
    password: admin123
```

**Problems:**
1. **RWO PVC for DAGs** - Cannot be shared across nodes
2. **No DAG deployment mechanism** - Files not syncing to pods
3. **No git-sync configured** - Alternative not implemented

### Database Configuration

**Airflow Metadata Database:**
- Location: `airflow-postgresql-0` pod
- Database: `postgres` (dedicated to Airflow)
- User: `postgres`
- Status: ✅ Operational
- Migration version: `29ce7909c52b` (correct for Airflow 3.0.2)

**Application Database (Separate):**
- Location: `databases/postgresql-primary-0`
- Database: `appdb`
- Schema: `financial_screener`
- DAG configurations present: ✅ 4 rows
- Exchange groups present: ✅ 4 rows

---

## 4. DAG Deployment Strategy Issues

### Current State: ❌ **BROKEN**

**Attempted Method:** DAG PVC with manual file copy

**Why It Failed:**
1. RWO PVC causes multi-attach conflicts
2. File copies to pods don't persist (ephemeral storage)
3. No automatic sync mechanism
4. Manual process not sustainable

### Recommended Solutions

#### Option A: Git-Sync (RECOMMENDED)

**Pros:**
- Automatic updates from Git repository
- No PVC needed
- Standard Airflow deployment pattern
- Works with multiple pods

**Cons:**
- Requires Git repository access from cluster
- Slight delay for DAG updates (sync interval)

**Implementation:**
```yaml
dags:
  persistence:
    enabled: false
  gitSync:
    enabled: true
    repo: https://github.com/<your-org>/financial-screener.git
    branch: main
    subPath: airflow/dags
    wait: 60  # Sync every 60 seconds
```

#### Option B: Custom Docker Image

**Pros:**
- DAGs baked into image
- No external dependencies
- Fast startup
- No PVC needed

**Cons:**
- Requires image rebuild for DAG updates
- Image distribution to all worker nodes
- Larger image size

**Implementation:**
Already created earlier: `custom-airflow:3.0.2-dags`

#### Option C: ReadWriteMany PVC

**Pros:**
- Allows multiple pods to access same PVC
- Supports manual updates

**Cons:**
- Requires NFS or similar distributed filesystem
- Longhorn may not support RWX natively
- Performance overhead

**Implementation:**
```yaml
dags:
  persistence:
    enabled: true
    accessMode: ReadWriteMany  # Requires storage class support
    storageClassName: nfs-client  # Example
```

#### Option D: ConfigMap (Small DAGs Only)

**Pros:**
- Simple, no PVC needed
- Automatic updates via kubectl

**Cons:**
- 1MB size limit per ConfigMap
- Not suitable for large DAG repositories

---

## 5. Backup Configuration Assessment

### Velero Backup Status: ✅ **OPERATIONAL**

**Backup Schedules:**
- Daily: 2:00 AM UTC (30-day retention)
- Weekly: Sundays 3:00 AM UTC (90-day retention)

**What's Backed Up:**
- ✅ Airflow namespace (all resources)
- ✅ PostgreSQL PVC (data-airflow-postgresql-0)
- ✅ Scheduler/Triggerer logs PVCs
- ✅ DAGs PVC (airflow-dags) - though currently broken

**PostgreSQL Backup Hooks:** ✅ **CONFIGURED**
- Pre-backup: `pg_start_backup('velero-backup', true)`
- Post-backup: `pg_stop_backup()`
- Applied to: `airflow-postgresql-0` pod and StatefulSet template

**Last Successful Backup:**
- Test backup: `airflow-test-20251029090751`
- Items backed up: 166
- Status: Completed
- Duration: 2 seconds

**Documentation:** ✅ **COMPREHENSIVE**
- File: `docs/BACKUP_AND_DISASTER_RECOVERY_STRATEGY.md`
- Sections: 16 (including all restore procedures)
- Status: Complete

---

## 6. Database-Driven DAG Configuration Assessment

### Configuration Status: ✅ **READY**

**Tables Created:**
1. `dag_configuration` - 4 rows for `historical_load_equities`
   - us_markets (NYSE, NASDAQ)
   - lse (LSE)
   - german_markets (Frankfurt, XETRA)
   - european_markets (Euronext, BME, SIX)

2. `exchange_groups` - 4 rows with timezone configs

**Sample Configuration:**
```sql
dag_name: historical_load_equities
job_name: us_markets
cpu_request: 500m
memory_request: 1Gi
batch_size: 500
```

**Assessment:** Configuration is ready but **cannot be tested** until DAGs are visible in Airflow.

---

## 7. Recommendations

### Immediate Actions (Priority 1) 🔴

1. **Fix PVC Multi-Attach Issue**
   ```bash
   # Option A: Disable DAG persistence and use git-sync
   helm upgrade airflow apache-airflow/airflow -n airflow \
     --set dags.persistence.enabled=false \
     --set dags.gitSync.enabled=true \
     --set dags.gitSync.repo=<your-git-repo> \
     --set dags.gitSync.branch=main \
     --set dags.gitSync.subPath=airflow/dags \
     --reuse-values

   # Option B: Delete stuck pods and disable DAG persistence
   kubectl delete pod airflow-scheduler-0 airflow-dag-processor-d55949988-69nzr -n airflow
   helm upgrade airflow apache-airflow/airflow -n airflow \
     --set dags.persistence.enabled=false \
     --reuse-values
   ```

2. **Deploy DAGs Properly**
   - Choose one of the 4 deployment strategies above
   - Git-sync recommended for production
   - Custom image acceptable for stable DAG code

3. **Verify Scheduler Starts**
   ```bash
   kubectl get pods -n airflow -w
   # Wait for scheduler to reach Running (2/2)
   ```

### Short-Term Actions (Priority 2) 🟡

4. **Copy DAGs to All Pods** (if using manual method temporarily)
   ```bash
   # Script to copy to all pods
   for POD in $(kubectl get pods -n airflow -o name | grep -E '(scheduler|dag-processor|api-server)'); do
     kubectl cp /tmp/airflow-dags.tar.gz $POD:/tmp/ -c <container>
     kubectl exec $POD -c <container> -- tar xzf /tmp/airflow-dags.tar.gz -C /opt/airflow/
   done
   ```

5. **Verify DAG Visibility**
   ```bash
   # Check serialized DAGs
   kubectl exec airflow-postgresql-0 -n airflow -- \
     psql -U postgres -d postgres -c "SELECT COUNT(*) FROM serialized_dag;"

   # Should show 3 DAGs (data_collection, historical_load, calculate_indicators)
   ```

### Long-Term Actions (Priority 3) 🟢

6. **Implement Git-Sync Properly**
   - Store DAGs in Git repository
   - Configure Helm chart with git-sync
   - Set appropriate sync interval (60-300 seconds)
   - Document DAG update process

7. **Configure Ingress for Airflow UI**
   - Currently accessible via `airflow.stratdata.org`
   - Verify TLS/SSL configuration
   - Document access procedures

8. **Set Up Monitoring**
   - DAG execution metrics
   - Task failure alerts
   - Scheduler health checks
   - Database connection pool monitoring

9. **Optimize Resource Allocation**
   - Scheduler: Currently struggling to start
   - Review CPU/memory requests and limits
   - Consider LocalExecutor vs CeleryExecutor

10. **Test Database-Driven DAG Configuration**
    - Once DAGs are visible, trigger `historical_load_equities`
    - Verify configuration loaded from `dag_configuration` table
    - Verify exchange groups used from database
    - Confirm kubectl pods created with correct resources

---

## 8. Testing Checklist

Once DAG deployment is fixed, verify:

- [ ] Scheduler Running (2/2 containers)
- [ ] 3 DAGs visible in UI (data_collection, historical_load, calculate_indicators)
- [ ] DAGs serialized in database (serialized_dag table has 3 rows)
- [ ] historical_load_equities DAG can be unpaused
- [ ] historical_load_equities DAG can be triggered
- [ ] Configuration loaded from financial_screener.dag_configuration table
- [ ] Kubectl pods created with resources from database config
- [ ] Indicators DAG triggered after historical_load completion
- [ ] Velero backup includes all components
- [ ] UI accessible at airflow.stratdata.org

---

## 9. Summary

### What's Working ✅
- API Server (UI) accessible
- PostgreSQL metadata database operational
- Triggerer running
- Backup infrastructure configured (Velero)
- Database-driven DAG configuration ready
- Comprehensive documentation created

### What's Broken ❌
- Scheduler stuck (PVC multi-attach issue)
- DAGs not visible (deployment mechanism broken)
- One DAG processor stuck (PVC conflict)
- No DAG execution possible

### Root Cause
Helm chart configured with `dags.persistence.enabled=true` and RWO PVC, causing:
1. Multi-attach conflicts blocking pods
2. No proper DAG sync mechanism
3. Manual file copies not persisting

### Recommended Solution
**Disable DAG persistence and implement git-sync:**
```bash
helm upgrade airflow apache-airflow/airflow -n airflow \
  --set dags.persistence.enabled=false \
  --set dags.gitSync.enabled=true \
  --set dags.gitSync.repo=https://github.com/<org>/financial-screener.git \
  --set dags.gitSync.branch=main \
  --set dags.gitSync.subPath=airflow/dags \
  --set dags.gitSync.wait=60 \
  --reuse-values
```

**Estimated Time to Fix:** 15-30 minutes
**Estimated Time to Full Operational:** 1 hour (including verification and testing)

---

**Assessment Date:** 2025-10-29
**Assessed By:** Claude Code
**Next Review:** After implementing recommended fixes
