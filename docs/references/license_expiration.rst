License Expiration Notifications
================================

Background and purpose
----------------------

A ``License`` has an expiration date determined by its associated ``SubscriptionPlan``'s expiration date.
We can (via internal configuration) send upcoming and post-facto license expiration emails
for particular enterprise customers (given their uuid).  When licenses approach expiration,
enabled customer learners will receive automated reminder emails via Braze, both as expiration approaches,
and after the plan has expired.
The learner expiration reminder system is designed to be idempotent and safe to run frequently (e.g., hourly).

Configuration
^^^^^^^^^^^^^

A cron job executes the management command on a schedule, and **only for the specified customer uuids**.

The expiration reminder system requires the following Django settings:

* ``BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN`` - The Braze campaign ID for expiration reminder emails
* Standard Braze API configuration (API key, URL, app ID)

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
