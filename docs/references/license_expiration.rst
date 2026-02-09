License Expiration
==================

Background
----------

* A ``License`` has an expiration date determined by its associated ``SubscriptionPlan``'s expiration date.
* When licenses approach expiration, learners can receive automated reminder emails via Braze.
* The expiration reminder system is designed to be idempotent and safe to run frequently (e.g., hourly).
* Once a license expires, it is no longer valid for course enrollment or activation.

Definitions
-----------
* **Expiration date** The date when a license becomes invalid, inherited from the subscription plan's expiration date.
* **Expiration reminder** An email notification sent to learners when their activated license is approaching expiration.
* **Expiration window** The configurable time period before expiration when reminders are sent (default: 30 days).
* **Expiration reminder sent date** A timestamp tracking when an expiration reminder email was sent to prevent duplicates.

License Lifecycle and Expiration
---------------------------------

A license progresses through various states during its lifecycle:

1. **Unassigned** - License is available but not assigned to any learner
2. **Assigned** - License is assigned to a learner but not yet activated
3. **Activated** - Learner has activated the license and can enroll in courses
4. **Revoked** - License has been revoked by an administrator
5. **Expired** - License has passed its expiration date (inherited from subscription plan)

Only **activated** licenses are eligible for expiration reminder emails. This is because:

* Unassigned licenses have no learner to notify
* Assigned but not activated licenses may never be used
* Revoked licenses are intentionally invalidated
* Activated licenses represent active learners who need advance notice

Expiration Reminder System
---------------------------

Configuration
^^^^^^^^^^^^^

The expiration reminder system requires the following Django settings:

* ``BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN`` - The Braze campaign ID for expiration reminder emails
* Standard Braze API configuration (API key, URL, app ID)

The reminder system also depends on:

* Enterprise customer data from the Enterprise API (for customer name, slug, etc.)
* A cron job or scheduled task runner to execute the management command

How Reminders Work
^^^^^^^^^^^^^^^^^^

1. **Query Phase**: The system queries for activated licenses where:

   * The associated subscription plan expires within the configured window (default: 30 days)
   * The license status is ``ACTIVATED``
   * The ``expiration_reminder_sent_date`` field is null (no reminder sent yet)
   * The licenses belong to the specified enterprise customer UUID(s)

2. **Email Sending Phase**: For each qualifying license:

   * Creates a Braze alias for the learner's email address
   * Sends a personalized Braze campaign message with:

     * Learner email
     * License UUID
     * Expiration date
     * Enterprise customer information (name, slug, sender alias)

   * On successful send, sets ``expiration_reminder_sent_date`` to current timestamp
   * On failure, leaves ``expiration_reminder_sent_date`` as null for retry

3. **Idempotency**: The ``expiration_reminder_sent_date`` field ensures:

   * Each license receives at most one expiration reminder
   * The cron can run frequently (hourly) without sending duplicates
   * Failed sends can be retried on subsequent runs

Management Command
^^^^^^^^^^^^^^^^^^

The ``send_license_expiration_reminders`` management command implements the reminder system:

.. code-block:: bash

    # Send reminders for a single enterprise customer (30 days before expiration)
    ./manage.py send_license_expiration_reminders \
        --enterprise-customer-uuid 12345678-1234-1234-1234-123456789012

    # Send reminders for multiple enterprise customers
    ./manage.py send_license_expiration_reminders \
        --enterprise-customer-uuid "uuid1,uuid2,uuid3"

    # Send reminders with custom expiration window (60 days)
    ./manage.py send_license_expiration_reminders \
        --enterprise-customer-uuid 12345678-1234-1234-1234-123456789012 \
        --days-before-expiration 60

    # Dry run to preview which licenses would be processed
    ./manage.py send_license_expiration_reminders \
        --enterprise-customer-uuid 12345678-1234-1234-1234-123456789012 \
        --dry-run

Command Arguments
^^^^^^^^^^^^^^^^^

* ``--enterprise-customer-uuid`` (required): UUID(s) of enterprise customer(s) to process

  * Can be a single UUID or multiple UUIDs separated by commas or spaces
  * Example: ``"uuid1,uuid2,uuid3"`` or ``"uuid1 uuid2 uuid3"``

* ``--days-before-expiration`` (optional, default: 30): Number of days before expiration to send reminder

  * Determines the expiration window
  * For example, ``--days-before-expiration 60`` sends reminders to licenses expiring in 60 days

* ``--dry-run`` (optional, default: false): Preview mode

  * Logs which licenses would be processed without sending actual emails
  * Useful for testing and validation

Database Schema
---------------

The ``License`` model includes the following expiration-related fields:

* ``subscription_plan`` (ForeignKey): Links to SubscriptionPlan which contains the expiration date
* ``expiration_reminder_sent_date`` (DateTimeField, nullable): Timestamp when expiration reminder was sent

  * Null = no reminder sent yet
  * Non-null = reminder already sent, skip this license
  * Used to implement idempotent reminder sending

The ``SubscriptionPlan`` model contains:

* ``expiration_date`` (DateTimeField): The date when all licenses in this plan expire

Recommended Cron Configuration
-------------------------------

The expiration reminder system is designed to run frequently without sending duplicate emails:

.. code-block:: bash

    # Run hourly to catch licenses entering the expiration window
    0 * * * * /path/to/manage.py send_license_expiration_reminders \
        --enterprise-customer-uuid "uuid1,uuid2,uuid3"

    # Or run daily if preferred
    0 9 * * * /path/to/manage.py send_license_expiration_reminders \
        --enterprise-customer-uuid "uuid1,uuid2,uuid3"

Benefits of frequent execution:

* Timely notifications: Licenses entering the expiration window are notified quickly
* Automatic retry: Failed email sends are retried on the next run
* No duplicate emails: ``expiration_reminder_sent_date`` prevents duplicate sends

Error Handling
--------------

The command handles various error scenarios:

Configuration Errors
^^^^^^^^^^^^^^^^^^^^

If required configuration is missing, the command raises a ``ValueError`` immediately:

* Missing ``BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN`` setting
* No valid enterprise customer UUIDs provided
* Enterprise API unreachable or returns errors

These errors stop execution for all enterprise customers since they indicate a systemic problem.

Email Sending Errors
^^^^^^^^^^^^^^^^^^^^

If an individual email fails to send (e.g., Braze API error):

* The error is logged with full traceback
* The ``expiration_reminder_sent_date`` is **not** set on the license
* Processing continues for other licenses
* The failed license will be retried on the next command run
* A summary of failures is logged at the end

Enterprise Processing Errors
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If processing fails for one enterprise customer (e.g., Enterprise API error):

* The error is logged with full traceback
* Processing continues for other enterprise customers in the list
* Total failure count includes the failed enterprise
* Command exits with non-zero status if any failures occurred

Monitoring and Observability
-----------------------------

The command provides comprehensive logging:

* **Start**: Logs total number of enterprise customers and configuration
* **Per-enterprise**: Logs number of licenses found for each enterprise customer
* **Per-license success**: Logs UUID, email, and expiration date
* **Per-license failure**: Logs full exception traceback
* **Completion**: Logs total success/failure counts across all enterprises

Example log output:

.. code-block:: text

    INFO Starting send_license_expiration_reminders command for 2 enterprise customer(s),
         days_before_expiration=30, dry_run=False
    INFO Processing enterprise 12345678-1234-1234-1234-123456789012,
         days_before_expiration=30, dry_run=False
    INFO Found 5 licenses to process for enterprise 12345678-1234-1234-1234-123456789012
    INFO Successfully sent license expiration reminder to user@example.com for license
         abcd-1234 expiring on 2026-03-15
    INFO Completed processing for enterprise 12345678-1234-1234-1234-123456789012.
         Success: 5, Failures: 0
    INFO Completed send_license_expiration_reminders command for 2 enterprise customer(s).
         Total Success: 8, Total Failures: 0

Integration with Renewals
--------------------------

License expiration and subscription plan renewals work together:

1. **Before Renewal**: As licenses approach expiration, learners receive reminder emails
2. **During Renewal**: A ``SubscriptionPlanRenewal`` can be created and processed
3. **After Renewal**: New licenses are created in the future plan with a new expiration date
4. **Reminder Reset**: New licenses in the renewed plan have null ``expiration_reminder_sent_date``
5. **Future Reminders**: As the renewed plan approaches expiration, the cycle repeats

See :doc:`renewals` for more details on subscription plan renewals.

Best Practices
--------------

1. **Run frequently**: Set up hourly or daily cron jobs to ensure timely notifications
2. **Monitor logs**: Watch for API errors, configuration issues, or unexpected patterns
3. **Use dry-run first**: Test with ``--dry-run`` before deploying to production
4. **Group enterprises**: Process multiple enterprise customers in a single command run for efficiency
5. **Coordinate with renewals**: Time renewal processing to happen after expiration reminders are sent
6. **Test Braze campaigns**: Verify Braze campaign content and configuration before enabling reminders
7. **Set appropriate window**: Choose ``--days-before-expiration`` based on customer needs (30-60 days typical)
