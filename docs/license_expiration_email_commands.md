# License Expiration Email Management Commands

A ``License`` has an expiration date determined by its associated ``SubscriptionPlan``'s expiration date.
We can (via internal configuration) send upcoming and post-facto license expiration emails
for particular enterprise customers (given their uuid).  When licenses approach expiration,
enabled customer learners will receive automated reminder emails via Braze, both as expiration approaches,
and after the plan has expired.
The learner expiration reminder system is designed to be idempotent and safe to run frequently (e.g., hourly).

This document describes the two management commands that send automated expiration-related emails to learners.

## Overview

| Command | Timing | Purpose |
|---------|--------|---------|
| `send_license_expiration_reminders` | **Before expiration** | Warn learners their license will expire soon |
| `send_subscription_plan_expiration_emails` | **After expiration** | Notify learners their subscription plan has expired |

---

## Learner Reminder Notification logic

### Command for reminders (upcoming expiration)
```bash
./manage.py send_license_expiration_reminders \
    --enterprise-customer-uuid <uuid> \
    --days-before-expiration 30
```

### Command Post-Expiration Notifications
```bash
./manage.py send_subscription_plan_expiration_emails \
    --enterprise-customer-uuid <uuid> \
    --days-since-expiration 7
```


### Intended Use Case
Proactively notify learners 30 days (configurable) before their activated license expires, giving them time to:
- Complete in-progress courses
- Contact their enterprise admin about renewals
- Plan for access loss

### Covered Subscription Plans
- Any plan belonging to a customer included in the uuid(s) passed to the mgmt command
- Plans with `expiration_date` within the next N days (default: 30)
- Only processes **activated** licenses (not assigned, unassigned, or revoked)

### Triggers
Runs every 30-60 minutes via cron

**Why frequent execution:**
- Idempotent design prevents duplicate emails via `expiration_reminder_sent_date` field
- Catches licenses entering expiration window throughout the day
- Automatic retry for failed email sends

### Emails Sent
**Braze Campaigns:** `BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN` and `BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN`

**Trigger Properties:**
- `enterprise_customer_slug`, `enterprise_customer_name`
- `enterprise_sender_alias`, `enterprise_contact_email`
- `expiration_date` (ISO 8601 format)
- `days_until_expiration` (integer, e.g., 30)
- `subscription_plan_title`

**Recipient:** Learner email from activated license

**Frequency:** Once per license (tracked via `expiration_reminder_sent_date`)

## Features

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
| Feb 13 | Pre-expiration learner reminders sent (30 days before) | `send_license_expiration_reminders` |
| Mar 15 | Subscription plan expires at midnight | (automatic) |
| Mar 16 | Post-expiration learner notifications sent (1 day after) | `send_subscription_plan_expiration_emails` |
| Mar 17-22 | Any failed post-expiration are retried for 6 more days | `send_subscription_plan_expiration_emails` |
