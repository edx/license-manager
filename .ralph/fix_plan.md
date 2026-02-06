# Ralph Fix Plan

## Architecture Overview

**License Manager** is a Django backend service for managing licenses and subscriptions for enterprise customers in the Open edX ecosystem.

### Core Applications
- **subscriptions/** - Main business logic for subscription plans, licenses, customer agreements, renewals
- **api/** - REST API endpoints, serializers, filters
- **api_client/** - Client libraries for external services (Enterprise, LMS, Braze, Enterprise Catalog)
- **core/** - Base models, shared utilities, authentication

### Key Models
- **SubscriptionPlan** - Subscription plans with licensing terms
- **License** - Individual licenses with status tracking (assigned, activated, revoked)
- **CustomerAgreement** - Enterprise customer agreements with renewal terms
- **Product** - Product definitions
- **LicenseEvent** - Historical tracking of license state changes

### External Integrations
- Enterprise Service, LMS, Enterprise Catalog, Braze

### Tech Stack
- Django + Django REST Framework
- Celery for background tasks
- MySQL database
- Redis (from devstack)
- Docker-based development

## High Priority
- [ ] Fix content caching logic in api/utils.py (investigate potential race conditions)
- [x] Add test coverage for LicenseTransferJob edge cases (Loop 2)
- [ ] Add new business logic to send a braze email reminder for a configurable enterprise customer uuid when an activated license is 30 days from expiring. It should be triggered via a management command.

## Medium Priority
- [ ] Review and fix duplicate license cleanup sorting logic
- [ ] Add integration tests for Braze campaigns with language settings

## Low Priority

## Completed
- [x] Project enabled for Ralph
- [x] Review codebase and understand architecture
- [x] Identify and document key components
- [x] Update AGENT.md with build/test/run commands
- [x] Conducted comprehensive codebase analysis (Loop 1)
- [x] Created comprehensive tests for BrazeApiClient (11 test methods)
- [x] Added test coverage for initialization errors and method calls
- [x] Improved exception handling in api/v1/views.py (replaced broad except clauses)
- [x] Updated comment in api/utils.py for clarity
- [x] Added 13 edge case tests for LicenseTransferJob (Loop 2)

## Notes
- Server: localhost:18170, admin: edx/edx
- Line length: 120 characters
- Focus on MVP functionality first
- Ensure each feature is properly tested
- Update this file after each major milestone

## Loop 1 Analysis Summary

### Test Coverage Analysis
- **Total test files**: 28 across the codebase
- **Missing test coverage**: BrazeApiClient had NO dedicated test file
- **Areas with limited tests**: API client layer (only 3 tests for enterprise client)

### Key Findings
1. **BrazeApiClient** - Completely untested integration layer (HIGH PRIORITY - FIXED)
2. **Recent features** - Enterprise default language support added in commits e306dbf/7d336f2
3. **Code quality** - 27+ exception handlers, several overly broad
4. **Potential bugs**:
   - License duplicate cleanup uses datetime.min fallback (edge case)
   - Auto-apply license may have race conditions
   - Silent AttributeError in renewal traversal

### Test Implementation (Loop 1)
- Created `test_braze_client.py` with 11 comprehensive test methods
- Tests cover:
  - Initialization with all required settings (5 tests)
  - Missing/empty configuration validation (6 tests)
  - Method calls (create_braze_alias, send_campaign_message)
  - Error handling for BrazeClientError
  - Trigger properties and recipients handling
- Follows existing codebase patterns (mocking, TestCase, override_settings)

### Files Modified (Loop 1)
- NEW: `/license_manager/apps/api_client/tests/test_braze_client.py` (236 lines)
- UPDATED: `.ralph/fix_plan.md` (added findings and priorities)

## Loop 2 Implementation Summary

### Task: Add test coverage for LicenseTransferJob edge cases

Added 13 comprehensive edge case tests to improve test coverage for the LicenseTransferJob model:

**Validation Tests:**
1. `test_validation_different_customer_agreements` - Ensures validation error when plans have different customer agreements
2. `test_validation_missing_transfer_criteria` - Ensures validation error when neither transfer_all nor license_uuids_raw is specified

**Delimiter Tests:**
3. `test_delimiter_comma` - Tests comma delimiter functionality
4. `test_delimiter_pipe` - Tests pipe delimiter functionality
5. `test_delimiter_char_property_default` - Tests default newline delimiter

**Data Handling Tests:**
6. `test_license_uuids_with_whitespace` - Ensures whitespace is properly stripped from UUIDs
7. `test_empty_license_uuids_raw` - Tests handling of empty UUID string

**Status Filtering Tests:**
8. `test_transfer_excludes_revoked_licenses` - Ensures revoked licenses are not transferred when transfer_all=False
9. `test_transfer_all_includes_all_statuses` - Ensures transfer_all=True includes licenses of all statuses

**Data Integrity Tests:**
10. `test_transfer_with_nonexistent_license_uuids` - Ensures non-existent UUIDs are gracefully ignored
11. `test_transfer_licenses_from_different_plan` - Ensures only licenses from old_plan are transferred

**Utility Tests:**
12. `test_get_customer_agreement_success` - Tests the get_customer_agreement method

### Previous Loop Changes (uncommitted):
- MODIFIED: `license_manager/apps/api/utils.py` - Updated comment for clarity
- MODIFIED: `license_manager/apps/api/v1/views.py` - Improved exception handling (replaced broad except with specific exceptions)

### Files Modified (Loop 2)
- MODIFIED: `license_manager/apps/subscriptions/tests/test_models.py` - Added 13 edge case tests (~220 lines)
- UPDATED: `.ralph/fix_plan.md` - Documented Loop 2 implementation
