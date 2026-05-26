# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

License Manager is a Django-based microservice within the Open edX ecosystem that manages enterprise customer licenses and subscriptions. It handles license lifecycle management, subscription plans, renewals, automated notifications, and integrates with various edX services for B2B educational content access.

## Test and Quality Instructions

- To run unit tests or generate coverage reports, invoke the `unit-tests` skill.
- To run quality checks (linting, style), invoke the `quality-tests` skill.

## Code Navigation

- Prefer using the LSP tool over grep/glob when navigating Python code (definitions, references, type info)

## Key Principles

- Search the codebase before assuming something isn't implemented
- Write comprehensive tests with clear documentation
- Follow Test-Driven Development when refactoring or modifying existing functionality
- Always write tests for new functionality you implement
- Keep changes focused and minimal
- Follow existing code patterns
- Prefer the `ddt` package for parameterized tests to reduce code duplication

## Documentation & Institutional Memory

- Document new functionality in `docs/references/`
- When you learn something important about how this codebase works (gotchas, non-obvious
  patterns, integration quirks), capture it in the relevant `docs/references/` file or
  in `docs/architecture-patterns.md`
- These docs are institutional memory - future sessions (yours or others) will benefit
  from what you record here

## Architecture Overview

This is a Django service for managing enterprise licenses and subscriptions, part of the Open edX ecosystem.
The `docs` folder contains extensive documentation including architecture overviews, ADRs (Architecture Decision Records),
and feature documentation. `docs/architecture_overview.rst` provides comprehensive details about the service architecture.

Always read `docs/architecture-patterns.md` before starting (if it exists).

### Core Applications

- **subscriptions** - Core business logic for subscription plans, licenses, customer agreements, renewals, and license events
- **api** - REST API endpoints with versioned views (v1/), serializers, filters, and pagination
- **api_client** - Client libraries for external services (Enterprise, LMS, Braze, Enterprise Catalog)
- **core** - Base models, shared utilities, authentication, permissions, and core Django functionality

### Key Concepts

- **SubscriptionPlan**: Defines subscription plans with licensing terms, enterprise associations, and expiration policies
- **License**: Individual licenses with status tracking (assigned, activated, revoked, etc.) and lifecycle management
- **CustomerAgreement**: Enterprise customer agreements with renewal terms, discount settings, and subscription plan associations
- **Product**: Product definitions that subscription plans are associated with for billing and catalog purposes
- **LicenseEvent**: Historical tracking of license state changes for audit trails
- **Auto-Assignment**: Licenses can be automatically assigned to learners upon login based on email domains
- **Renewals**: Automated renewal processing for subscription plans with configurable policies
- **License Transfer**: Ability to transfer licenses between subscription plans for the same customer

### External Service Integration

- **Enterprise Service**: Customer and learner data, enterprise catalog associations
- **LMS**: Course enrollment, user management, and authentication
- **Enterprise Catalog**: Course catalog management and content validation
- **Braze**: Email notifications, marketing automation, and license expiration reminders
- **Salesforce**: Billing and bookkeeping system identifier references (not direct integration)

### Background Tasks

- Celery-based task processing for subscription renewals, license operations, and bulk processing
- Management commands for license expiration emails, data processing, and maintenance operations
- Scheduled tasks for automated license lifecycle management

### Local Development

- This service is included in the [edx/devstack](https://github.com/openedx/devstack) repository for integration testing alongside the rest of the Open edX ecosystem
- Server runs on `localhost:18170`
- Uses MySQL 8.0, Redis, and Celery worker
- Docker-based development environment with docker-compose

## Testing Notes

- Uses pytest with Django integration
- Coverage reporting enabled by default
- PII annotation checks required for Django models

## Before opening a PR or pushing a branch

Run a self-check on the diff before creating a PR or pushing:
1. Compute effective LoC — exclude lockfiles, generated files, snapshots, and vendor code.
2. Count effective touched files — exclude the above plus one-to-one test pairs.
3. If effective LoC > 400 or effective files > 10, stop and propose a split before proceeding.
4. Report the result inline before continuing.
