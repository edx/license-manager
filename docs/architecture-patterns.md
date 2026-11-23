# Architecture Patterns

This document captures reusable patterns and institutional knowledge for the License Manager service.

## Overview

The License Manager follows Django best practices with a focus on license lifecycle management,
subscription handling, and integration with the Open edX ecosystem. This document records patterns
that future development sessions should follow.

## Common Patterns

### License Status Management

Licenses follow a state machine pattern with specific allowed transitions:

- `unassigned` -> `assigned` -> `activated` -> `revoked`
- Licenses can be "unrevoked" under certain conditions (see ADR 0005)
- Status transitions are primarily audited via `django-simple-history` (`License.history`)
  together with the `status` and related date fields on `License`
- `LicenseEvent` records are used for certain triggered workflows (for example, specific
  management commands), not as a required record for every status transition

When modifying license status, update the `License` fields consistently so the change is
captured in model history. Create `LicenseEvent` records only where the workflow explicitly
uses them for additional event tracking.

### Subscription Plan Renewals

Subscription plans support automated renewal processing:

- Renewals are handled via Celery tasks
- New licenses are created for renewed subscriptions
- Old licenses can be transferred or revoked based on configuration
- See `docs/references/renewals.rst` for detailed renewal workflows

### Feature Toggling

All new features should be released behind Waffle feature gates:

- Use `Switch` for simple boolean toggles affecting all users
- Use `Flag` for granular control (specific users, percentages, criteria)
- Clean up feature gates after permanent rollout

### Auto-Assignment

Licenses can be auto-assigned to learners based on email domains:

- Configured via `SubscriptionPlan.auto_apply_licenses` setting
- Triggered on learner login/authentication
- See ADR 0010 for design decisions

## API Patterns

### Versioned APIs

All public APIs are versioned under `api/v1/`:

- Use Django REST Framework serializers
- Implement filtering via `django_filters`
- Provide pagination for list endpoints
- Follow RESTful conventions

### Permission Model

The service uses role-based access control:

- `SUBSCRIPTIONS_ADMIN_ROLE` - Full subscription management
- `SUBSCRIPTIONS_LEARNER_ROLE` - Learner-level access
- `SYSTEM_ENTERPRISE_ADMIN_ROLE` - Enterprise administrator
- Additional roles defined in `subscriptions/constants.py`

## External Integration Patterns

### API Clients

All external service calls go through dedicated client classes in `api_client/`:

- `enterprise.py` - Enterprise service integration
- `lms.py` - LMS API calls
- `braze.py` - Email notification sending
- `enterprise_catalog.py` - Catalog validation

Clients extend `base_oauth.py` for OAuth2 authentication.

### Email Notifications

Email notifications are sent via Braze:

- Use management commands for bulk email operations
- Implement idempotency for retry safety
- Track email sending in license events or logs
- See `docs/license_expiration_email_commands.md` for examples

## Testing Patterns

### Test Organization

- Unit tests use `pytest` with Django integration
- Use `ddt` (data-driven tests) for parameterized test cases
- Mock external API calls using `unittest.mock`
- Test factories for model creation (if using `factory_boy`)

### Coverage Requirements

- PII annotations required on all Django models (see `.pii_annotations.yml`)
- Coverage reporting enabled by default
- Run quality checks via `make quality`

## Database Patterns

### Historical Tracking

The service uses `django-simple-history` for model history:

- License state changes tracked via `LicenseEvent`
- Important model changes tracked via historical tables
- Enables audit trails and compliance reporting

### Performance Considerations

- Use `select_related()` and `prefetch_related()` for query optimization
- License queries can be expensive; consider pagination and filtering
- Bulk operations preferred over individual saves in loops

## Gotchas and Common Issues

### License Assignment Race Conditions

License assignment can face race conditions in high-concurrency scenarios:

- Use database transactions with appropriate isolation levels
- Consider ADR 0014 (linearizable license assignment) for critical paths
- Test concurrent assignment scenarios

### Email Domain Matching

Auto-assignment based on email domains requires careful validation:

- Handle subdomains appropriately
- Consider case-sensitivity in email addresses
- Validate domain allowlists before assignment

### Course Unenrollment on License Revocation

`execute_post_revocation_tasks` (`apps/api/tasks.py`) picks the edx-enterprise endpoint by the
license's *original* status (ENT-12360):

- `ACTIVATED` -> `revoke_course_enrollments_for_user_task` -> `licensed-enterprise-course-enrollment/license_revoke/`.
  This is **user + enterprise scoped**, not license scoped: it terminates every licensed enrollment the
  learner has in that enterprise. That is intentional, because renewals mint a *new* license UUID while
  existing enrollments keep the old one.
- `ASSIGNED` (pending) -> `license_expiration_task` -> `.../bulk_licensed_enrollments_expiration/`
  with the revoked license's UUID **plus every UUID in its renewal chain** (followed via `License.renewed_from`).
  Pending licenses can carry enrollments (admin Bulk Enrollment), may have no `lms_user_id` (which
  `license_revoke` rejects with a 400), and must not touch enrollments the learner holds under another
  license. The chain matters because renewal copies pending licenses to new UUIDs too, and enrollments keep
  the UUID they were made under. `license_expiration_task` runs on `LoggedTaskWithRetry`, so transient
  edx-enterprise failures (including its 422 for partial failure) are retried; this is safe because
  already-revoked licensed enrollments are skipped downstream.
- Any other status (for example, already `REVOKED`) triggers no unenrollment, and `revoke_license` raises
  `LicenseRevocationError` first. If you add a status to `REVOCABLE_LICENSE_STATUSES`, add a matching branch:
  `test_every_revocable_status_triggers_unenrollment` fails until you do.

Known gap: edx-enterprise `PendingEnrollment` rows (bulk-enrolled learners with no LMS account yet) are not
cleaned up by either endpoint.

### Renewal Processing Timing

Renewal processing is time-sensitive:

- Consider timezone handling for expiration dates
- Account for grace periods in business logic
- Test edge cases around midnight boundaries

### `request.user.id` Is Not an LMS User Id

license-manager's `core.User` has no LMS user id, and `JWT_AUTH` doesn't map the JWT `user_id` claim onto it,
so `request.user.id` is the local primary key. Use `UserDetailsFromJwtMixin.lms_user_id` (or the JWT `user_id`)
when an LMS id is needed. `LicenseAction.actor_lms_user_id` is populated from `request.user.id` despite its name;
see `docs/references/license_audit_trail.rst`.

## Future Considerations

This section should be updated as new patterns emerge or architectural decisions are made.
Refer to `docs/decisions/` for formal Architecture Decision Records (ADRs).
