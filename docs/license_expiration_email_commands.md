# License Expiration Email Management Commands

This document describes the two management commands that send automated expiration-related emails to learners.

## Overview

| Command | Timing | Purpose |
|---------|--------|---------|
| `send_license_expiration_reminders` | **Before expiration** | Warn learners their license will expire soon |
| `send_subscription_plan_expiration_emails` | **After expiration** | Notify learners their subscription plan has expired |

---

## Pre-Expiration Reminders

### Command
```bash
./manage.py send_license_expiration_reminders \
    --enterprise-customer-uuid <uuid> \
    --days-before-expiration 30
```

### Intended Use Case
Proactively notify learners 30 days (configurable) before their activated license expires, giving them time to:
- Complete in-progress courses
- Contact their enterprise admin about renewals
- Plan for access loss

### Covered Subscription Plans
- Plans with `expiration_date` within the next N days (default: 30)
- Plans associated with the specified enterprise customer UUID(s)
- Only processes **activated** licenses (not assigned, unassigned, or revoked)

### Triggers
**Recommended:** Run every 30-60 minutes via cron

```bash
# Run every 30 minutes
*/30 * * * * /path/to/manage.py send_license_expiration_reminders \
    --enterprise-customer-uuid "uuid1,uuid2,uuid3"
```

**Why frequent execution:**
- Idempotent design prevents duplicate emails via `expiration_reminder_sent_date` field
- Catches licenses entering expiration window throughout the day
- Automatic retry for failed email sends

### Emails Sent
**Braze Campaign:** `BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN`

**Trigger Properties:**
- `enterprise_customer_slug`, `enterprise_customer_name`
- `enterprise_sender_alias`, `enterprise_contact_email`
- `expiration_date` (ISO 8601 format)
- `days_until_expiration` (integer, e.g., 30)
- `subscription_plan_title`

**Recipient:** Learner email from activated license

**Frequency:** Once per license (tracked via `expiration_reminder_sent_date`)

### Log Keywords

**Success indicators:**
```
INFO Starting send_license_expiration_reminders command for
INFO Found N licenses to process for enterprise
INFO Sent license expiration reminder email to
INFO Completed processing for enterprise ... Success: N, Failures: 0
INFO Completed send_license_expiration_reminders command ... Total Success: N
```

**Failure indicators:**
```
ERROR Failed to send expiration reminder for license
ERROR Failed to get enterprise customer data for
WARNING No activated licenses found
ERROR BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN setting is not configured
```

**Tracking:**
- License UUID in success/failure messages
- User email in success messages
- Success/failure counts per enterprise and total

---

## Post-Expiration Notifications

### Command
```bash
./manage.py send_subscription_plan_expiration_emails \
    --enterprise-customer-uuid <uuid> \
    --days-since-expiration 7
```

### Intended Use Case
Notify learners within 7 days (configurable) after their subscription plan expires, informing them that:
- Their access has ended
- They should contact their enterprise admin for renewal
- Their license is no longer valid for course enrollment

### Covered Subscription Plans
- Plans with `expiration_date` in the past N days (default: 7)
- Plans that expired **yesterday or earlier** (today's expirations excluded)
- Plans associated with the specified enterprise customer UUID(s)
- Only processes **activated** licenses

### Triggers
**Recommended:** Run every 30-60 minutes via cron

```bash
# Run every 30 minutes
*/30 * * * * /path/to/manage.py send_subscription_plan_expiration_emails \
    --enterprise-customer-uuid "uuid1,uuid2,uuid3"
```

**Why frequent execution:**
- Same idempotency benefits as pre-expiration reminders
- Uses `subscription_plan_expiration_email_sent_date` to prevent duplicates
- Ensures timely notification after expiration confirmation

### Emails Sent
**Braze Campaign:** `BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN`

**Trigger Properties:**
- `enterprise_customer_slug`, `enterprise_customer_name`
- `enterprise_sender_alias`, `enterprise_contact_email`
- `expiration_date` (ISO 8601 format)
- `days_since_expiration` (integer, e.g., 3)
- `subscription_plan_title`

**Recipient:** Learner email from activated license

**Frequency:** Once per license (tracked via `subscription_plan_expiration_email_sent_date`)

### Log Keywords

**Success indicators:**
```
INFO Starting send_subscription_plan_expiration_emails command for
INFO Found N licenses to process for enterprise
INFO Sent subscription plan expiration email to
INFO Completed processing for enterprise ... Success: N, Failures: 0
INFO Completed send_subscription_plan_expiration_emails command ... Total Success: N
```

**Failure indicators:**
```
ERROR Failed to send subscription plan expiration email for license
ERROR Failed to get enterprise customer data for
WARNING No activated licenses found with subscription plans expired in the last
ERROR BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN setting is not configured
```

**Tracking:**
- License UUID in success/failure messages
- User email in success messages
- Success/failure counts per enterprise and total

---

## Common Features

### Multiple Enterprise Support
Both commands support processing multiple enterprises in one execution:
```bash
# Comma-separated
--enterprise-customer-uuid "uuid1,uuid2,uuid3"

# Space-separated
--enterprise-customer-uuid "uuid1 uuid2 uuid3"
```

### Dry Run Mode
Test without sending actual emails:
```bash
--dry-run
```

Logs which licenses would be processed without triggering Braze campaigns.

### Error Handling
- **Configuration errors** (missing Braze campaign): Stop immediately with `ValueError`
- **Individual email failures**: Log error, continue processing other licenses, raise exception at end
- **Enterprise API failures**: Log error, continue processing other enterprises, raise exception at end

### Database Tracking
Both commands use dedicated timestamp fields to prevent duplicate emails:
- Pre-expiration: `License.expiration_reminder_sent_date`
- Post-expiration: `License.subscription_plan_expiration_email_sent_date`

Set to current UTC time on successful email send, remains `NULL` on failure for retry.

---

## Timeline Example

For a subscription plan expiring on **March 15, 2026**:

| Date | Event | Command |
|------|-------|---------|
| Feb 13 | Pre-expiration reminder sent (30 days before) | `send_license_expiration_reminders` |
| Mar 15 | Subscription plan expires at midnight | (automatic) |
| Mar 16 | Post-expiration notification sent (1 day after) | `send_subscription_plan_expiration_emails` |
| Mar 17-22 | Post-expiration notifications continue for newly expired plans | `send_subscription_plan_expiration_emails` |
| Mar 23+ | Plans expired >7 days ago no longer eligible | (outside window) |
