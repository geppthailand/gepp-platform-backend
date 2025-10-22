# Cron Job Setup for AI Audit Queue Processing

This document explains how to set up the cron job to process AI audit batches automatically.

## Overview

The AI audit system uses an asynchronous queue-based approach:

1. **User triggers audit** → Creates `transaction_audit_history` record with `status='in_progress'`
2. **Cron job runs** → Processes all `in_progress` batches
3. **Results saved** → Updates batch record to `status='completed'` with audit results

## Cron Job Options

### Option 1: AWS Lambda Scheduled Event (Recommended for AWS)

If deployed on AWS Lambda, use CloudWatch Events to trigger the queue processor:

```yaml
# serverless.yml or SAM template
functions:
  processAuditQueue:
    handler: GEPPPlatform.services.cores.transaction_audit.cron_process_audit_queue.main
    events:
      - schedule:
          rate: rate(1 minute)  # Run every minute
          enabled: true
```

### Option 2: System Crontab (Linux/Unix)

For traditional server deployments, add to crontab:

```bash
# Edit crontab
crontab -e

# Add this line to run every minute
* * * * * cd /path/to/gepp-platform/backend && python -m GEPPPlatform.services.cores.transaction_audit.cron_process_audit_queue >> /var/log/gepp-audit-cron.log 2>&1
```

### Option 3: Manual API Trigger (Testing/Development)

For testing or manual processing, call the API endpoint:

```bash
# Trigger queue processing manually
curl -X POST https://your-api.com/api/transaction_audit/process_queue \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

## How It Works

### 1. User Triggers Audit

When user clicks "Start AI Audit" in the frontend:

```
POST /api/transaction_audit/add_ai_audit_queue
```

This endpoint:
- Sets transactions `ai_audit_status` to `'queued'`
- Creates `transaction_audit_history` record with `status='in_progress'`
- Returns immediately (no blocking)

### 2. Cron Job Processes Queue

The cron job (`cron_process_audit_queue.py`):
- Fetches all `transaction_audit_history` records where `status='in_progress'`
- For each batch:
  - Gets queued transactions
  - Calls OpenAI API to audit each transaction
  - Updates transaction statuses
  - Calculates token usage
  - Updates batch record to `status='completed'`

### 3. User Views Results

User can view completed audits in the "Audit History" tab, which shows:
- Batch ID
- Processing status (In Progress / Completed / Failed)
- Number of transactions processed
- Approved/Rejected counts
- Token usage statistics

## Environment Variables

Ensure these are set:

```bash
OPENAI_API_KEY=your-openai-api-key
DATABASE_URL=postgresql://user:pass@host:port/dbname
```

## Monitoring

### Check Cron Status

```bash
# View cron logs
tail -f /var/log/gepp-audit-cron.log

# Check for in_progress batches
psql -d gepp -c "SELECT id, organization_id, status, started_at FROM transaction_audit_history WHERE status='in_progress';"
```

### Database Queries

```sql
-- Count batches by status
SELECT status, COUNT(*) as count
FROM transaction_audit_history
GROUP BY status;

-- Find stuck batches (in_progress for > 1 hour)
SELECT id, organization_id, started_at
FROM transaction_audit_history
WHERE status='in_progress'
  AND started_at < NOW() - INTERVAL '1 hour';
```

## Troubleshooting

### Batches stuck in 'in_progress'

If batches are stuck, check:

1. **Cron job running?**
   ```bash
   ps aux | grep cron_process_audit_queue
   ```

2. **OpenAI API key valid?**
   ```bash
   echo $OPENAI_API_KEY
   ```

3. **Database connection working?**
   ```bash
   psql $DATABASE_URL -c "SELECT 1"
   ```

4. **Manual trigger:**
   ```bash
   python -m GEPPPlatform.services.cores.transaction_audit.cron_process_audit_queue
   ```

### Cron Not Running

- Check cron service: `systemctl status cron`
- Verify crontab: `crontab -l`
- Check permissions on script
- Verify Python path in crontab

## Performance Tuning

### Adjust Processing Frequency

For high-volume systems, adjust the cron schedule:

```bash
# Every 30 seconds (requires two cron entries)
* * * * * /path/to/script.sh
* * * * * sleep 30 && /path/to/script.sh
```

### Batch Size Limits

The cron job processes ALL in_progress batches. To limit concurrent processing:

1. Add batch locking mechanism
2. Process only N oldest batches
3. Add organization-level rate limiting

### Token Usage Optimization

Monitor token usage in audit_info summary:

```sql
SELECT
  id,
  audit_info->'summary'->'token_usage'->>'total_tokens' as total_tokens,
  total_transactions
FROM transaction_audit_history
WHERE status='completed'
ORDER BY created_date DESC
LIMIT 10;
```

## Security

- Ensure cron script runs as appropriate user (not root)
- Protect OpenAI API key
- Log rotation for cron logs
- Database connection security

## Development Mode

For local development, you can disable the cron and trigger manually:

```bash
# Run once
python -m GEPPPlatform.services.cores.transaction_audit.cron_process_audit_queue

# Or use the API endpoint
curl -X POST http://localhost:8000/api/transaction_audit/process_queue
```
