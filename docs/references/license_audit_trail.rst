License Audit Trail
===================

Background
----------

* ``LicenseAction`` (``subscriptions/models.py``) is the audit log of actions performed on licenses.
  It mirrors ``LearnerContentAssignmentAction`` in enterprise-access.
* Rows are append-only. ``license`` and ``subscription_plan`` are foreign keys without database constraints,
  so a row outlives a deleted license; never ``select_related('license')`` when reading history.
* The plan stored on a row is the plan the action happened under. Renewal rows are written on the
  *renewed* plan's licenses, and licenses moved by a ``LicenseTransferJob`` keep their earlier rows on the old plan.

What is recorded
----------------

+------------------+----------------------------------------------------------------+---------------+------------------------------------------+
| ``action_type``  | Written by                                                     | ``actor_type``| ``source``                               |
+==================+================================================================+===============+==========================================+
| ``assigned``     | ``LicenseAdminViewSet.assign``                                 | admin         | ``admin_api_bulk``                       |
+------------------+----------------------------------------------------------------+---------------+------------------------------------------+
| ``activated``    | ``LicenseActivationView``; auto-apply (``auto_applied`` in     | learner       | ``api``                                  |
|                  | metadata)                                                      |               |                                          |
+------------------+----------------------------------------------------------------+---------------+------------------------------------------+
| ``revoked``      | ``execute_post_revocation_tasks`` (bulk-revoke, revoke-all)    | admin/system  | ``admin_api_bulk``, ``admin_api``,       |
|                  |                                                                |               | ``celery_task``                          |
+------------------+----------------------------------------------------------------+---------------+------------------------------------------+
| ``renewed``      | ``renew_subscription`` (provisioning API, Django admin,        | admin/system  | ``api``, ``admin_ui``, ``renewal_job``   |
|                  | ``process_renewals``)                                          |               |                                          |
+------------------+----------------------------------------------------------------+---------------+------------------------------------------+

Not recorded yet: reminders, email notifications and their delivery outcome, plan expiration,
``retire_old_licenses`` status changes, duplicate-license cleanup and admin license deletion.
``expired``, ``deleted``, ``snapshot_revert`` and ``plan_maintenance`` are defined but never written.
The model has no ``status``/``error_reason``/``completed_at`` fields, so success or failure is not tracked.

Actor ids
---------

``actor_lms_user_id`` holds the license-manager ``core.User`` primary key (writers pass ``request.user.id``),
**not** an LMS user id: license-manager's JWT settings don't map the ``user_id`` claim onto ``User``.
Resolve actors against the local ``User`` table, never against LMS. ``learner_lms_user_id`` *is* an LMS user id.

Reading history
---------------

``GET /api/v1/subscriptions/{subscription_uuid}/audit-history/`` (``LicenseActionViewSet``)

* Requires ``SUBSCRIPTIONS_ADMIN_ACCESS_PERMISSION`` on the plan's enterprise customer; other customers' admins
  get a 403, unknown or malformed plan UUIDs a 404.
* Paginated with ``LicensePagination`` (``page``, ``page_size`` up to 500).
* Filters (``LicenseActionFilter``): ``action_type``, ``actor_type``, ``source`` (comma-separated, validated
  against the model choices), ``license_uuid``, ``learner_email`` (case-insensitive), ``created_after`` and
  ``created_before`` (inclusive; dates or datetimes, UTC unless an offset is given), and ``ordering``
  (``-created`` by default, or ``created``; ``uuid`` breaks ties).
* ``actor`` is ``{"email", "full_name"}`` resolved in one query per page, or ``null`` for system actions and
  users that no longer exist (e.g. retired).
* ``metadata`` is limited to ``LicenseActionSerializer.ALLOWED_METADATA_KEYS``; add a key there before exposing it.

Example response::

    {
      "count": 1, "next": null, "previous": null, "num_pages": 1,
      "results": [{
        "uuid": "9fc1cad3-6f1a-4c75-995d-a23bef6a0f68",
        "created": "2026-10-29T11:11:58.577831Z",
        "action_type": "revoked",
        "actor_type": "admin",
        "actor": {"email": "admin@example.com", "full_name": "Admin User"},
        "source": "admin_api_bulk",
        "license_uuid": "d7687e08-07ae-480d-b7e5-9a9f1b9e90a3",
        "learner_email": "learner1@example.com",
        "correlation_id": "0f8a4b9e-5c1d-4d7e-9a43-1b2c3d4e5f60",
        "metadata": {"original_status": "activated"}
      }]
    }

Privacy
-------

``License.clear_historical_pii()`` nulls ``learner_email``, ``learner_lms_user_id``, ``learner_external_key`` and the
``learner_external_key`` metadata key on the license's ``LicenseAction`` rows. It runs during user retirement
(``UserRetirementView``) and in the ``retire_old_licenses`` purge; the audit events themselves are kept.
