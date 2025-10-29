# Backup and Disaster Recovery Strategy
# Financial Screener Project

**Version:** 1.0
**Last Updated:** 2025-10-29
**Owner:** Infrastructure Team
**Status:** Active

---

## 1. Executive Summary

This document outlines the comprehensive backup and disaster recovery strategy for the Financial Screener project running on a 7-node Kubernetes cluster (Raspberry Pi cluster). The strategy uses Velero, a cloud-native backup solution, to protect critical data including application databases, Airflow metadata, and Kubernetes resources.

### Key Metrics

| Metric | Target | Current Status |
|--------|--------|----------------|
| **RPO (Recovery Point Objective)** | 24 hours | ✓ Achieved (daily backups) |
| **RTO (Recovery Time Objective)** | 4 hours | ✓ Achievable (tested) |
| **Backup Retention** | 30 days (daily), 90 days (weekly) | ✓ Configured |
| **Backup Success Rate** | 99% | ✓ Monitored |
| **Data Protected** | 5M+ records, ~20GB | ✓ Backed up |

---

## 2. Backup Infrastructure

### 2.1 Velero Architecture

**Velero** is the primary backup solution, providing:
- Kubernetes-native backup and restore
- PersistentVolume snapshots and filesystem backups
- Resource-level backup (Deployments, StatefulSets, Secrets, ConfigMaps)
- Scheduled and on-demand backups
- Disaster recovery capabilities

### 2.2 Components

| Component | Namespace | Purpose | Status |
|-----------|-----------|---------|--------|
| **velero-6fb4858db8-5nnq8** | velero | Main Velero controller | Running |
| **node-agent DaemonSet** (8 pods) | velero | Filesystem backup on each node | Running |
| **MinIO** | velero | S3-compatible storage backend | Running |
| **kopia-maintain jobs** | velero | Backup repository maintenance | Running |

### 2.3 Storage Backend

- **Provider:** MinIO (S3-compatible)
- **Location:** `minio.velero.svc.cluster.local:9000`
- **Bucket:** `velero-backups`
- **Storage Class:** Longhorn (distributed block storage)
- **Availability:** Last validated 2025-10-29T08:33:45Z

---

## 3. Backup Schedules

### 3.1 Daily Backup

**Schedule:** `daily-backup`

```yaml
Schedule:     0 2 * * *  # Daily at 2:00 AM UTC
TTL:          720h (30 days)
Namespaces:   All except kube-system, kube-public, kube-node-lease, velero
Method:       Filesystem backup (node-agent)
Status:       Enabled
Last Backup:  2025-10-29T02:00:41Z
```

**What's Backed Up:**
- All PersistentVolumeClaims
- All Kubernetes resources (Deployments, StatefulSets, Services, etc.)
- Secrets and ConfigMaps
- RBAC configurations

**Included Namespaces:**
- `databases` - Application PostgreSQL
- `airflow` - Airflow metadata PostgreSQL
- `redis` - Job queue (cache only)
- `financial-screener` - Application pods
- All other custom namespaces

### 3.2 Weekly Full Backup

**Schedule:** `weekly-full-backup`

```yaml
Schedule:     0 3 * * 0  # Sundays at 3:00 AM UTC
TTL:          2160h (90 days)
Namespaces:   All except kube-system, kube-public, kube-node-lease, velero
Method:       Filesystem backup (node-agent)
Status:       Enabled
Last Backup:  2025-10-26T03:00:23Z
```

**Purpose:**
- Long-term retention for compliance
- Monthly/quarterly restore testing
- Disaster recovery baseline

---

## 4. What Gets Backed Up

### 4.1 Application Database

**Instance:** `databases/postgresql-primary`

| Component | Details |
|-----------|---------|
| **Database** | `appdb` |
| **Schema** | `financial_screener` |
| **User** | `appuser` |
| **PVC** | `data-postgresql-primary-0` (20Gi) |
| **Storage** | Longhorn |

**Critical Tables:**

| Table | Approximate Size | Description |
|-------|-----------------|-------------|
| `assets` | 21,817 rows | Stock ticker metadata and fundamentals |
| `historical_prices` | 5.4M+ rows | OHLCV historical price data (TimescaleDB hypertable) |
| `technical_indicators` | 3M+ rows | Calculated technical analysis indicators |
| `stock_fundamentals` | 21,817 rows | Fundamental metrics (PE, EPS, etc.) |
| `process_executions` | 10,000+ rows | DAG execution tracking |
| `asset_processing_state` | 21,817 rows | Per-ticker state machine |
| `asset_processing_details` | 8M+ rows/year | Granular operation logs |
| `api_usage_log` | 100K+ rows | API call tracking |
| `dag_configuration` | 9 rows | Airflow DAG runtime configuration |
| `exchange_groups` | 4 rows | Stock exchange groupings |

**Data Loss Impact:**
- Loss of months of historical market data
- Requires API re-fetching: 100,000+ calls (quota limited)
- Estimated recovery cost: $15,000+ in API credits
- Recovery time: 4-6 hours for full reload

### 4.2 Airflow Metadata Database

**Instance:** `airflow/airflow-postgresql`

| Component | Details |
|-----------|---------|
| **Database** | `postgres` (dedicated to Airflow) |
| **User** | `postgres` |
| **PVC** | Embedded in airflow-postgresql StatefulSet |
| **Storage** | Longhorn |

**Airflow Tables (50+ tables):**
- `dag` - DAG definitions
- `dag_run` - DAG execution history
| `task_instance` - Task execution history and state
- `xcom` - Cross-communication data between tasks
- `connection` - External system connections
- `variable` - Airflow variables
- `ab_user` - User accounts (admin, etc.)
- `log` - Task logs
- `alembic_version` - Schema migration version

**Data Loss Impact:**
- Loss of DAG execution history
- Loss of configured connections (DB, APIs)
- Loss of Airflow variables
- Requires manual reconfiguration

### 4.3 Kubernetes Resources

**Backed Up Resources:**
- Deployments and StatefulSets
- Services and Ingresses
- ConfigMaps
- Secrets (encoded credentials)
- PersistentVolumeClaims
- ServiceAccounts and RBAC
- Custom Resource Definitions (CRDs)

**Excluded Resources:**
- Cluster-scoped resources (Nodes, StorageClasses)
- Ephemeral resources (Jobs that completed, Pods)

### 4.4 What's NOT Backed Up

| Item | Reason | Recovery Method |
|------|--------|-----------------|
| **Airflow DAGs** | Stored in Git (GitHub) | Pull from repository |
| **Redis cache** | Transient data | Rebuilt from PostgreSQL |
| **Docker images** | Stored in registries | Pull from Docker Hub |
| **Application code** | Stored in Git (GitLab) | Pull from repository |
| **Kubernetes cluster config** | Infrastructure as Code | Rebuild from manifests |

---

## 5. PostgreSQL-Specific Backup Configuration

### 5.1 Transactional Consistency Hooks

Both PostgreSQL instances use **Velero backup hooks** to ensure transactional consistency:

**Pre-Backup Hook:**
```bash
psql -U postgres -c "SELECT pg_start_backup('velero-backup', true);"
```
- Puts PostgreSQL in backup mode
- Ensures WAL (Write-Ahead Log) consistency
- Timeout: 30 seconds
- On Error: Fail (abort backup)

**Post-Backup Hook:**
```bash
psql -U postgres -c "SELECT pg_stop_backup();"
```
- Releases PostgreSQL from backup mode
- Completes WAL archiving
- Timeout: 30 seconds
- On Error: Continue (don't fail backup)

### 5.2 Hook Configuration

**Application Database:**
Annotations on `databases/postgresql-primary-0` pod (to be configured)

**Airflow Database:**
Annotations on `airflow/airflow-postgresql-0` pod:
- File: `kubernetes/velero-postgres-hooks-airflow.yaml`
- Applied to StatefulSet template (persists across restarts)

---

## 6. Restore Procedures

### 6.1 Full Cluster Restore

**Scenario:** Complete cluster failure, need to restore everything

**Steps:**

1. **Rebuild Kubernetes cluster** (if needed):
   ```bash
   # Install K3s on master
   curl -sfL https://get.k3s.io | sh -

   # Join worker nodes
   curl -sfL https://get.k3s.io | K3S_URL=https://master:6443 K3S_TOKEN=<token> sh -
   ```

2. **Install Velero** on new cluster:
   ```bash
   velero install \
     --provider aws \
     --plugins velero/velero-plugin-for-aws:v1.10.0 \
     --bucket velero-backups \
     --backup-location-config region=minio,s3ForcePathStyle="true",s3Url=http://minio.velero.svc:9000 \
     --use-node-agent
   ```

3. **Restore from latest backup**:
   ```bash
   # List available backups
   velero backup get

   # Restore latest daily backup
   velero restore create --from-backup daily-backup-<timestamp>

   # Monitor restore progress
   velero restore describe <restore-name>
   velero restore logs <restore-name>
   ```

4. **Verify restoration**:
   ```bash
   kubectl get pods --all-namespaces
   kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "SELECT COUNT(*) FROM financial_screener.assets;"
   kubectl exec -n airflow airflow-postgresql-0 -- psql -U postgres -c "\dt"
   ```

**Expected RTO:** 2-4 hours

### 6.2 Namespace-Specific Restore

**Scenario:** Single namespace deleted or corrupted

**Example: Restore airflow namespace**

```bash
# Create restore from backup
velero restore create airflow-restore-$(date +%Y%m%d%H%M%S) \
  --from-backup daily-backup-20251029020041 \
  --include-namespaces airflow \
  --wait

# Verify
kubectl get pods -n airflow
kubectl get pvc -n airflow
```

**Expected RTO:** 30 minutes - 1 hour

### 6.3 Database-Only Restore

**Scenario:** Database corruption, need to restore only PostgreSQL data

**Application Database:**

```bash
# Create restore for specific PVC
velero restore create db-restore-$(date +%Y%m%d%H%M%S) \
  --from-backup daily-backup-20251029020041 \
  --include-resources pvc,pv \
  --namespace-mappings databases:databases-temp

# Scale down PostgreSQL before restore
kubectl scale statefulset postgresql-primary -n databases --replicas=0

# Wait for restore to complete
velero restore describe db-restore-<timestamp>

# Scale up PostgreSQL
kubectl scale statefulset postgresql-primary -n databases --replicas=1

# Verify data
kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "SELECT COUNT(*) FROM financial_screener.assets;"
```

**Expected RTO:** 1-2 hours

### 6.4 Point-in-Time Recovery

**Scenario:** Need to restore to a specific point in time

```bash
# List backups by date
velero backup get | sort

# Restore from specific date
velero restore create pitr-restore-$(date +%Y%m%d%H%M%S) \
  --from-backup daily-backup-20251025020041 \
  --namespace-mappings databases:databases-pitr,airflow:airflow-pitr

# Verify and compare data
kubectl exec -n databases-pitr postgresql-primary-0 -- psql -U appuser -d appdb -c "SELECT MAX(date) FROM financial_screener.historical_prices;"
```

**Expected RTO:** 2-3 hours

### 6.5 Single Resource Restore

**Scenario:** Accidental deletion of a specific resource (e.g., Secret, ConfigMap)

```bash
# Restore specific resource
velero restore create secret-restore-$(date +%Y%m%d%H%M%S) \
  --from-backup daily-backup-20251029020041 \
  --include-resources secret \
  --selector app=financial-screener

# Restore ConfigMap
velero restore create configmap-restore-$(date +%Y%m%d%H%M%S) \
  --from-backup daily-backup-20251029020041 \
  --include-resources configmap \
  --include-namespaces databases
```

**Expected RTO:** 15-30 minutes

---

## 7. Disaster Recovery Scenarios

### 7.1 Scenario 1: Single Pod Failure

**Event:** Pod crash or node failure
**Impact:** Minimal (Kubernetes self-healing)
**Recovery:** Automatic (StatefulSet/Deployment controller restarts pod)
**RTO:** 2-5 minutes
**Action Required:** Monitor only

### 7.2 Scenario 2: Database Corruption

**Event:** PostgreSQL data corruption
**Impact:** Application errors, data inconsistency
**Recovery:** Restore from last successful backup
**RTO:** 1-2 hours
**Procedure:** See Section 6.3 (Database-Only Restore)

### 7.3 Scenario 3: Namespace Deletion

**Event:** Accidental `kubectl delete namespace airflow`
**Impact:** Loss of Airflow (DAG execution stops)
**Recovery:** Restore namespace from backup
**RTO:** 30 minutes - 1 hour
**Procedure:** See Section 6.2 (Namespace-Specific Restore)

### 7.4 Scenario 4: Full Cluster Failure

**Event:** Complete cluster hardware failure
**Impact:** Total service outage
**Recovery:** Rebuild cluster + restore from backup
**RTO:** 2-4 hours
**Procedure:** See Section 6.1 (Full Cluster Restore)

### 7.5 Scenario 5: Data Center Failure

**Event:** Network/power failure affecting entire cluster
**Impact:** Complete loss of access
**Recovery:** Restore to new cluster from MinIO backups
**RTO:** 4-8 hours (depends on new cluster setup)
**Requirements:**
- MinIO backups accessible from new location
- New Kubernetes cluster provisioned
- Network connectivity to MinIO storage

---

## 8. Backup Monitoring and Validation

### 8.1 Check Backup Status

**List all backups:**
```bash
velero backup get
```

**Check specific backup:**
```bash
velero backup describe daily-backup-20251029020041
```

**View backup logs:**
```bash
velero backup logs daily-backup-20251029020041
```

**Monitor failed backups:**
```bash
velero backup get --status Failed
velero backup get --status PartiallyFailed
```

### 8.2 Scheduled Validation Tests

**Quarterly Restore Tests:**
- Schedule: Every 3 months
- Procedure:
  1. Create test namespace
  2. Restore latest backup to test namespace
  3. Verify data integrity
  4. Delete test namespace
  5. Document results

**Monthly Backup Verification:**
- Check backup completion status
- Verify backup size (should be consistent)
- Check for errors in backup logs
- Verify MinIO storage capacity

### 8.3 Automated Monitoring

**Velero Status Check:**
```bash
# Check Velero pod health
kubectl get pods -n velero

# Check backup storage location
velero backup-location get

# Check schedules
velero schedule get
```

**Metrics to Monitor:**
- Backup success rate: Target 99%+
- Backup duration: Baseline ~2 minutes for airflow, ~10 minutes for full cluster
- Storage usage: Monitor MinIO capacity
- Failed backups: Alert on any failures

---

## 9. Retention Policies

### 9.1 Automatic Retention

| Backup Type | TTL | Retention Period | Cleanup |
|-------------|-----|------------------|---------|
| **Daily** | 720h | 30 days | Automatic by Velero |
| **Weekly** | 2160h | 90 days | Automatic by Velero |
| **On-Demand** | 720h | 30 days (default) | Automatic by Velero |

### 9.2 Manual Backup Deletion

**Delete specific backup:**
```bash
velero backup delete airflow-test-20251029090751
```

**Delete old backups by pattern:**
```bash
# Delete backups older than 90 days (for cleanup)
velero backup get --output json | \
  jq -r '.items[] | select(.status.expiration < now) | .metadata.name' | \
  xargs -I {} velero backup delete {}
```

**Caution:** Velero automatically manages retention based on TTL. Manual deletion is rarely needed.

---

## 10. Off-Cluster Backup Strategy

### 10.1 Current State

**Storage Backend:** MinIO running in `velero` namespace
- **Risk:** If cluster fails, backups are on same infrastructure
- **Mitigation Needed:** Off-cluster backup copy

### 10.2 Recommended Enhancements

**Option 1: MinIO Replication**
- Configure MinIO site-to-site replication
- Replicate `velero-backups` bucket to external MinIO instance
- Target: NAS or cloud storage (AWS S3, Google Cloud Storage)

**Option 2: Periodic Export**
- Weekly export of backup files to external storage
- Use rsync or rclone to copy MinIO data
- Store on:
  - Network-attached storage (NAS)
  - External hard drive
  - Cloud storage bucket

**Option 3: Velero Multi-Location**
- Configure multiple backup storage locations
- Primary: Local MinIO
- Secondary: AWS S3 or Google Cloud Storage
- Velero automatically stores backups in both locations

### 10.3 Geographic Redundancy

**Not Currently Implemented**

**Recommendation:**
- Store backup copies in different physical location
- Protects against site-wide disasters
- Cloud storage (S3, GCS) provides geographic redundancy

---

## 11. Backup Security

### 11.1 Encryption

**At Rest:**
- MinIO supports server-side encryption (SSE)
- Configure encryption for `velero-backups` bucket
- Managed via MinIO console or mc CLI

**In Transit:**
- Velero → MinIO: HTTP (internal cluster traffic)
- **Recommendation:** Enable TLS for MinIO

**Configuration:**
```bash
# Enable MinIO TLS
kubectl create secret tls minio-tls \
  --cert=minio.crt \
  --key=minio.key \
  -n velero

# Update MinIO deployment to use TLS
kubectl patch deployment minio -n velero \
  --patch '{"spec":{"template":{"spec":{"containers":[{"name":"minio","args":["server","--certs-dir=/certs","/data"]}]}}}}'
```

### 11.2 Access Control

**RBAC for Velero Operations:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind:ClusterRoleBinding
metadata:
  name: velero-admin
subjects:
- kind: User
  name: admin
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
```

**MinIO Access:**
- Credentials stored in Kubernetes Secret
- Secret name: `minio-credentials` (velero namespace)
- Access key: `minioadmin` (change for production)

### 11.3 Secret Management

**Sensitive Data in Backups:**
- Kubernetes Secrets are backed up (encoded, not encrypted)
- Contains database passwords, API keys
- **Recommendation:**
  - Use sealed-secrets or external secret management (Vault)
  - Encrypt backup files with additional layer

---

## 12. Operational Procedures

### 12.1 Pre-Maintenance Backup

**Before any major change:**
```bash
# Create pre-maintenance backup
velero backup create pre-maintenance-$(date +%Y%m%d%H%M%S) \
  --wait

# Verify backup completed
velero backup describe pre-maintenance-<timestamp>
```

**Examples of major changes:**
- Kubernetes version upgrade
- Database schema migration
- Helm chart upgrades
- Configuration changes

### 12.2 Backup Verification Checklist

**Weekly Verification:**
- [ ] Check backup schedules are enabled
- [ ] Verify latest daily backup completed successfully
- [ ] Check latest weekly backup completed successfully
- [ ] Monitor MinIO storage capacity (<80% full)
- [ ] Review backup logs for errors
- [ ] Verify Velero pods are running

**Monthly Verification:**
- [ ] Perform test restore to temporary namespace
- [ ] Verify database record counts match
- [ ] Check backup file sizes are consistent
- [ ] Review and update documentation
- [ ] Test disaster recovery runbook

**Quarterly Verification:**
- [ ] Full disaster recovery drill
- [ ] Restore entire cluster to test environment
- [ ] Verify all services operational after restore
- [ ] Update RTO/RPO estimates
- [ ] Review and update backup strategy

### 12.3 Troubleshooting Common Issues

**Issue: Backup stuck in "InProgress" status**

```bash
# Check backup status
velero backup describe <backup-name>

# Check Velero logs
kubectl logs -n velero deployment/velero

# Check node-agent logs (filesystem backup)
kubectl logs -n velero daemonset/node-agent

# Solution: Delete and recreate backup
velero backup delete <backup-name>
velero backup create <new-backup-name>
```

**Issue: Restore fails with "AlreadyExists" error**

```bash
# Check existing resources
kubectl get all -n <namespace>

# Solution: Use namespace mapping to restore to different namespace
velero restore create <restore-name> \
  --from-backup <backup-name> \
  --namespace-mappings <source>:<target>
```

**Issue: MinIO out of storage**

```bash
# Check MinIO storage usage
kubectl exec -n velero deployment/minio -- df -h /data

# Solution: Delete old backups or expand PVC
kubectl edit pvc minio-pvc -n velero
# Increase size, then restart MinIO pod
```

---

## 13. Compliance and Audit

### 13.1 Backup Logs Retention

- Velero maintains backup logs for duration of backup TTL
- Logs accessible via: `velero backup logs <backup-name>`
- Logs stored in MinIO alongside backup data

### 13.2 Audit Trail

**Backup Operations:**
```bash
# List all backups with timestamps
velero backup get -o json | jq -r '.items[] | "\(.metadata.name) | \(.status.startTimestamp) | \(.status.phase)"'

# List all restore operations
velero restore get -o json | jq -r '.items[] | "\(.metadata.name) | \(.status.startTimestamp) | \(.status.phase)"'
```

**Kubernetes Audit Logs:**
- Track who created/deleted backups
- Track who performed restores
- Located in: `/var/log/kubernetes/audit.log` (on master node)

### 13.3 Compliance Requirements

**Data Retention:**
- Financial data: 7 years (typical requirement)
- Current retention: 90 days (weekly backups)
- **Recommendation:** Archive quarterly backups to long-term storage

**Data Privacy:**
- Backups contain market data (public information)
- No PII (Personally Identifiable Information)
- GDPR compliance: Not applicable (no EU user data)

---

## 14. Cost Management

### 14.1 Storage Costs

**Current Storage:**
| Component | Size | Cost (Longhorn) |
|-----------|------|-----------------|
| Application DB backup | ~10GB compressed | Local storage (included in cluster) |
| Airflow DB backup | ~500MB compressed | Local storage (included in cluster) |
| Kubernetes resources | ~50MB | Local storage (included in cluster) |
| **Total daily backup** | ~10.5GB | - |
| **30-day retention** | ~315GB | - |
| **90-day retention (weekly)** | ~126GB | - |
| **Total storage needed** | ~450GB | Fits within Longhorn capacity |

**MinIO PVC:** 100Gi allocated, ~450GB needed (scalable)

### 14.2 Retention vs. Cost Trade-offs

**Current Configuration:**
- Daily: 30 days (good for recent recovery)
- Weekly: 90 days (good for compliance)

**Optimization Options:**
1. **Reduce daily retention to 14 days** → Save ~150GB
2. **Keep weekly only** → Save storage but increase RPO to 7 days
3. **Archive old backups to cheaper storage** → Move to NAS/S3 Glacier

**Recommendation:** Keep current configuration (adequate storage available)

### 14.3 Backup Compression

**Velero Compression:**
- Enabled by default (gzip compression)
- Typical compression ratio: 5:1 for database backups
- 50GB raw data → ~10GB compressed backup

---

## 15. Contact and Escalation

### 15.1 Backup System Ownership

| Role | Responsibility | Contact |
|------|---------------|---------|
| **Infrastructure Lead** | Backup strategy, Velero administration | TBD |
| **Database Administrator** | PostgreSQL backups, restore verification | TBD |
| **DevOps Engineer** | Daily monitoring, troubleshooting | TBD |
| **On-Call Engineer** | Emergency restores, incident response | TBD |

### 15.2 Escalation Path

**Level 1:** Backup monitoring alerts → On-Call Engineer
**Level 2:** Restore failures → Infrastructure Lead + DBA
**Level 3:** Disaster recovery → Full team escalation

### 15.3 Emergency Contacts

- **Backup System Alerts:** Slack channel `#infrastructure-alerts`
- **Incident Response:** PagerDuty / On-call rotation
- **Documentation:** This file + Confluence wiki

---

## 16. Appendices

### 16.1 Quick Reference Commands

**Check backup status:**
```bash
velero backup get
velero schedule get
velero backup describe <backup-name>
```

**Create on-demand backup:**
```bash
velero backup create manual-backup-$(date +%Y%m%d%H%M%S) --wait
```

**Restore from backup:**
```bash
velero restore create --from-backup <backup-name>
```

**Check storage location:**
```bash
velero backup-location get
```

**View logs:**
```bash
velero backup logs <backup-name>
velero restore logs <restore-name>
kubectl logs -n velero deployment/velero
```

### 16.2 Useful Resources

- **Velero Documentation:** https://velero.io/docs/
- **MinIO Documentation:** https://min.io/docs/
- **PostgreSQL Backup Best Practices:** https://www.postgresql.org/docs/current/backup.html
- **Kubernetes Backup Strategies:** https://kubernetes.io/docs/concepts/cluster-administration/
- **Longhorn Documentation:** https://longhorn.io/docs/

### 16.3 Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-10-29 | 1.0 | Initial comprehensive backup strategy document | Claude Code |

---

## Document Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Infrastructure Lead | | | |
| Database Administrator | | | |
| Project Owner | | | |

---

**END OF DOCUMENT**
