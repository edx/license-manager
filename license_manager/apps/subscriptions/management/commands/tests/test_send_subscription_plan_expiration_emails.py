"""
Tests for the send_subscription_plan_expiration_emails management command.
"""
from datetime import datetime, timedelta, timezone
from unittest import mock
from uuid import uuid4

import ddt
import pytest
from braze.exceptions import BrazeClientError
from django.core.management import call_command
from django.test import TestCase, override_settings

from license_manager.apps.subscriptions.constants import (
    ACTIVATED,
    ASSIGNED,
    REVOKED,
)
from license_manager.apps.subscriptions.models import (
    CustomerAgreement,
    License,
    SubscriptionPlan,
)
from license_manager.apps.subscriptions.tests.factories import (
    CustomerAgreementFactory,
    LicenseFactory,
    SubscriptionPlanFactory,
)
from license_manager.apps.subscriptions.utils import localized_utcnow


@ddt.ddt
@pytest.mark.django_db
class SendSubscriptionPlanExpirationEmailsTests(TestCase):
    """
    Tests for the send_subscription_plan_expiration_emails management command.
    """
    command_name = 'send_subscription_plan_expiration_emails'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.enterprise_customer_uuid = uuid4()
        cls.customer_agreement = CustomerAgreementFactory(
            enterprise_customer_uuid=cls.enterprise_customer_uuid
        )

    def tearDown(self):
        """
        Cleanup after each test.
        """
        super().tearDown()
        License.objects.all().delete()
        SubscriptionPlan.objects.all().delete()
        CustomerAgreement.objects.all().delete()

    def _create_subscription_with_licenses(self, expiration_days_ago, num_licenses=1, license_status=ACTIVATED):
        """
        Helper to create a subscription plan with licenses that expired in the past.

        Args:
            expiration_days_ago (int): Number of days ago the subscription expired
            num_licenses (int): Number of licenses to create
            license_status (str): Status of the licenses to create

        Returns:
            tuple: (SubscriptionPlan, list of Licenses)
        """
        now = localized_utcnow()
        expiration_date = now - timedelta(days=expiration_days_ago)

        subscription_plan = SubscriptionPlanFactory(
            customer_agreement=self.customer_agreement,
            start_date=now - timedelta(days=365),
            expiration_date=expiration_date,
            is_active=True,
        )

        licenses = []
        for _ in range(num_licenses):
            license_obj = LicenseFactory(
                subscription_plan=subscription_plan,
                status=license_status,
                user_email=f'user{uuid4()}@example.com',
                lms_user_id=12345,
            )
            licenses.append(license_obj)

        return subscription_plan, licenses

    def test_no_licenses_found(self):
        """
        Test that the command handles the case when no expired subscriptions are found.
        """
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )
            assert any('No activated licenses found' in msg for msg in log.output)

    def test_dry_run_mode(self):
        """
        Test that dry run mode logs licenses without sending emails.
        """
        # Create licenses with subscription plans expired 3 days ago
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=2
        )

        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
                dry_run=True,
            )

            # Verify dry run messages
            assert any('DRY RUN' in msg for msg in log.output)
            assert any(str(licenses[0].uuid) in msg for msg in log.output)
            assert any(str(licenses[1].uuid) in msg for msg in log.output)

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_send_emails_success(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test successful sending of subscription plan expiration emails.
        """
        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create licenses with subscription plans expired 3 days ago
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=2
        )

        # Run command
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

            # Verify success messages
            assert any('Success: 2' in msg for msg in log.output)

        # Verify Braze API was called correctly
        assert mock_create_braze_alias.call_count == 2
        assert mock_braze_instance.send_campaign_message.call_count == 2

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_only_activated_licenses_processed(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that only activated licenses are processed, not assigned or revoked licenses.
        """
        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create subscription plan expired 3 days ago
        now = localized_utcnow()
        expiration_date = now - timedelta(days=3)

        subscription_plan = SubscriptionPlanFactory(
            customer_agreement=self.customer_agreement,
            start_date=now - timedelta(days=365),
            expiration_date=expiration_date,
            is_active=True,
        )

        # Create activated, assigned, and revoked licenses
        activated_license = LicenseFactory(
            subscription_plan=subscription_plan,
            status=ACTIVATED,
            user_email='activated@example.com',
            lms_user_id=12345,
        )
        LicenseFactory(
            subscription_plan=subscription_plan,
            status=ASSIGNED,
            user_email='assigned@example.com',
        )
        LicenseFactory(
            subscription_plan=subscription_plan,
            status=REVOKED,
            user_email='revoked@example.com',
        )

        # Run command
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

            # Verify only 1 license was processed (the activated one)
            assert any('Success: 1' in msg for msg in log.output)

        # Verify only one email was sent
        assert mock_braze_instance.send_campaign_message.call_count == 1

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_custom_days_since_expiration(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that custom days_since_expiration parameter works correctly.
        """
        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create license with subscription plan expired 10 days ago
        self._create_subscription_with_licenses(
            expiration_days_ago=10,
            num_licenses=1
        )

        # Create license with subscription plan expired outside the 14 day threshold
        self._create_subscription_with_licenses(
            expiration_days_ago=15,
            num_licenses=1
        )

        # Run command with 14 days threshold
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=14,
            )

            # Verify success
            assert any('Success: 1' in msg for msg in log.output)

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_braze_client_error_handling(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that Braze API errors are handled properly.
        """
        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        # Make Braze client raise an error
        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.side_effect = BrazeClientError('Braze API error')
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create licenses
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=1
        )

        # Run command - should raise exception due to failures
        with pytest.raises(Exception, match='subscription plan license expiration emails failed to send'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_filters_by_enterprise_customer(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that the command only processes licenses for the specified enterprise customer.
        """
        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create licenses for the specified enterprise
        subscription_plan1, licenses1 = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=2
        )

        # Create licenses for a different enterprise
        different_enterprise_uuid = uuid4()
        different_customer_agreement = CustomerAgreementFactory(
            enterprise_customer_uuid=different_enterprise_uuid
        )
        now = localized_utcnow()
        expiration_date = now - timedelta(days=3)
        different_subscription = SubscriptionPlanFactory(
            customer_agreement=different_customer_agreement,
            start_date=now - timedelta(days=365),
            expiration_date=expiration_date,
            is_active=True,
        )
        LicenseFactory(
            subscription_plan=different_subscription,
            status=ACTIVATED,
            user_email='different@example.com',
            lms_user_id=99999,
        )

        # Run command for the first enterprise only
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

            # Verify only 2 licenses were processed (not the one from the different enterprise)
            assert any('Success: 2' in msg for msg in log.output)

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN=None)
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    def test_missing_braze_campaign_setting(self, mock_enterprise_client):
        """
        Test that the command raises an error if the Braze campaign setting is not configured.
        """
        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        # Create licenses
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=1
        )

        # Run command - should raise ValueError
        with pytest.raises(ValueError, match='BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN setting is not configured'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    def test_enterprise_api_error_handling(self, mock_enterprise_client):
        """
        Test that Enterprise API errors are handled properly.
        """
        # Make Enterprise API raise an error
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.side_effect = Exception('Enterprise API error')

        # Create licenses
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=1
        )

        # Enterprise API errors should cause the command to fail with an exception
        with pytest.raises(Exception, match='subscription plan license expiration emails failed to send'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @ddt.data(',', ' ')
    def test_multiple_enterprise_customers_separators(self, separator, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that the command can process multiple enterprise customers separated by commas or spaces
        """
        # Create second enterprise customer
        second_enterprise_uuid = uuid4()
        second_customer_agreement = CustomerAgreementFactory(
            enterprise_customer_uuid=second_enterprise_uuid
        )

        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value

        def get_enterprise_data(uuid):
            if str(uuid) == str(self.enterprise_customer_uuid):
                return {
                    'uuid': str(self.enterprise_customer_uuid),
                    'slug': 'test-enterprise-1',
                    'name': 'Test Enterprise 1',
                    'contact_email': 'contact1@example.com',
                    'default_language': 'en',
                }
            else:
                return {
                    'uuid': str(second_enterprise_uuid),
                    'slug': 'test-enterprise-2',
                    'name': 'Test Enterprise 2',
                    'contact_email': 'contact2@example.com',
                    'default_language': 'en',
                }

        mock_enterprise_instance.get_enterprise_customer_data.side_effect = get_enterprise_data

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create licenses for first enterprise (2 licenses)
        subscription_plan1, licenses1 = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=2
        )

        # Create licenses for second enterprise (3 licenses)
        now = localized_utcnow()
        expiration_date = now - timedelta(days=3)
        subscription_plan2 = SubscriptionPlanFactory(
            customer_agreement=second_customer_agreement,
            start_date=now - timedelta(days=365),
            expiration_date=expiration_date,
            is_active=True,
        )
        for _ in range(3):
            LicenseFactory(
                subscription_plan=subscription_plan2,
                status=ACTIVATED,
                user_email=f'user{uuid4()}@example.com',
                lms_user_id=12345,
            )

        # Run command with comma-separated UUIDs
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=f'{self.enterprise_customer_uuid}{separator}{second_enterprise_uuid}',
                days_since_expiration=7,
            )

            # Verify both enterprises were processed
            assert any('2 enterprise customer(s)' in msg for msg in log.output)
            assert any('Total Success: 5' in msg for msg in log.output)

        # Verify Braze API was called for all 5 licenses
        assert mock_create_braze_alias.call_count == 5
        assert mock_braze_instance.send_campaign_message.call_count == 5

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_multiple_enterprise_customers_one_has_no_licenses(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that the command continues processing when one enterprise has no expired subscriptions.
        """
        # Create second enterprise customer
        second_enterprise_uuid = uuid4()
        second_customer_agreement = CustomerAgreementFactory(
            enterprise_customer_uuid=second_enterprise_uuid
        )

        # Setup mocks
        mock_enterprise_instance = mock_enterprise_client.return_value

        def get_enterprise_data(uuid):
            if str(uuid) == str(self.enterprise_customer_uuid):
                return {
                    'uuid': str(self.enterprise_customer_uuid),
                    'slug': 'test-enterprise-1',
                    'name': 'Test Enterprise 1',
                    'contact_email': 'contact1@example.com',
                    'default_language': 'en',
                }
            else:
                return {
                    'uuid': str(second_enterprise_uuid),
                    'slug': 'test-enterprise-2',
                    'name': 'Test Enterprise 2',
                    'contact_email': 'contact2@example.com',
                    'default_language': 'en',
                }

        mock_enterprise_instance.get_enterprise_customer_data.side_effect = get_enterprise_data

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create licenses for first enterprise only (2 licenses)
        subscription_plan1, licenses1 = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=2
        )

        # Second enterprise has no expired subscriptions

        # Run command with both UUIDs
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=f'{self.enterprise_customer_uuid},{second_enterprise_uuid}',
                days_since_expiration=7,
            )

            # Verify both enterprises were processed
            assert any('2 enterprise customer(s)' in msg for msg in log.output)
            assert any('Total Success: 2' in msg for msg in log.output)
            assert any(f'No activated licenses found' in msg for msg in log.output)

        # Verify Braze API was called only for first enterprise's 2 licenses
        assert mock_create_braze_alias.call_count == 2
        assert mock_braze_instance.send_campaign_message.call_count == 2

    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.localized_utcnow'
    )
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @ddt.data(
        # One minute before Feb 11: still within Feb 10 calendar date, expiration 6 days ago is included
        {'mocked_now': datetime(2026, 2, 10, 23, 59, 0, tzinfo=timezone.utc), 'message_sent': True},
        # Feb 11 at midnight: window is exactly 7 days back; expiration 7 days ago is included
        {'mocked_now': datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc), 'message_sent': True},
        # Feb 11 mid-morning: same calendar date, still includes expirations from 7 days ago
        {'mocked_now': datetime(2026, 2, 11, 0, 30, 0, tzinfo=timezone.utc), 'message_sent': True},
        # Feb 11 late evening: still includes expirations from 7 days ago (Feb 4)
        {'mocked_now': datetime(2026, 2, 11, 23, 30, 0, tzinfo=timezone.utc), 'message_sent': True},
        # Feb 12 at midnight: window targets past 7 days (Feb 5-11), Feb 4 is 8 days ago and out of range
        {'mocked_now': datetime(2026, 2, 12, 0, 0, 0, tzinfo=timezone.utc), 'message_sent': False},
    )
    @ddt.unpack
    def test_days_since_expiration_uses_calendar_dates(
        self, mock_create_braze_alias, mock_enterprise_client, mock_utcnow, mocked_now, message_sent
    ):
        """
        Regression test: days_since_expiration must be calculated via calendar date
        subtraction, not datetime subtraction.

        The fix compares `.date()` portions so the result is always the correct calendar-day
        count regardless of the time-of-day component.

        The data cases verify the expiration window query boundaries: only licenses whose
        subscription expired in the past N calendar days are selected, regardless of what
        time of day the command runs. The window is [today - N days, today), excluding
        today's expirations to wait for confirmation they are actually expired.
        """
        mock_utcnow.return_value = mocked_now

        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Subscription expires at midnight on Feb 4 — exactly 7 calendar days before Feb 11.
        expiration_date = datetime(2026, 2, 4, 0, 0, 0, tzinfo=timezone.utc)
        subscription_plan = SubscriptionPlanFactory(
            customer_agreement=self.customer_agreement,
            start_date=datetime(2025, 2, 4, 0, 0, 0, tzinfo=timezone.utc),
            expiration_date=expiration_date,
            is_active=True,
        )

        LicenseFactory(
            subscription_plan=subscription_plan,
            status=ACTIVATED,
            user_email='user@example.com',
            lms_user_id=12345,
        )

        call_command(
            self.command_name,
            enterprise_customer_uuid=str(self.enterprise_customer_uuid),
            days_since_expiration=7,
        )

        if message_sent:
            assert mock_braze_instance.send_campaign_message.call_count == 1
            trigger_properties = mock_braze_instance.send_campaign_message.call_args[1]['trigger_properties']
            # days_since_expiration is calculated as the difference between today and expiration date
            # For Feb 10: Feb 10 - Feb 4 = 6 days
            # For Feb 11: Feb 11 - Feb 4 = 7 days
            days_diff = (mocked_now.date() - datetime(2026, 2, 4, 0, 0, 0, tzinfo=timezone.utc).date()).days
            assert trigger_properties['days_since_expiration'] == days_diff
        else:
            assert mock_braze_instance.send_campaign_message.call_count == 0

    def test_empty_enterprise_customer_uuids(self):
        """
        Test that the command raises an error when no UUIDs are provided.
        """
        with pytest.raises(ValueError, match='No valid enterprise customer UUIDs provided'):
            call_command(
                self.command_name,
                enterprise_customer_uuid='   ',
                days_since_expiration=7,
            )

    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    def test_subscription_plan_expiration_email_sent_date_set_on_success(
        self, mock_enterprise_client, mock_create_braze_alias
    ):
        """
        Test that subscription_plan_expiration_email_sent_date is set when email is successfully sent.
        """
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create license with subscription plan expired 3 days ago
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=1
        )
        license_obj = licenses[0]

        # Verify subscription_plan_expiration_email_sent_date is initially None
        assert license_obj.subscription_plan_expiration_email_sent_date is None

        # Run the command
        call_command(
            self.command_name,
            enterprise_customer_uuid=str(self.enterprise_customer_uuid),
            days_since_expiration=7,
        )

        # Refresh license from database
        license_obj.refresh_from_db()

        # Verify subscription_plan_expiration_email_sent_date is now set
        assert license_obj.subscription_plan_expiration_email_sent_date is not None

    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    def test_licenses_with_email_already_sent_are_skipped(self, mock_enterprise_client, mock_create_braze_alias):
        """
        Test that licenses that already have subscription_plan_expiration_email_sent_date set are skipped.
        """
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.return_value = None
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create 3 licenses with subscription plans expired 3 days ago
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=3
        )

        # Mark first license as already having received an email
        now = localized_utcnow()
        licenses[0].subscription_plan_expiration_email_sent_date = now - timedelta(days=1)
        licenses[0].save()

        # Run the command
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

            # Should only find 2 licenses (the ones without subscription_plan_expiration_email_sent_date)
            assert any('Found 2 licenses to process' in msg for msg in log.output)

        # Verify Braze API was called only for the 2 licenses without the email
        assert mock_create_braze_alias.call_count == 2
        assert mock_braze_instance.send_campaign_message.call_count == 2

    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @mock.patch(
        'license_manager.apps.subscriptions.management.commands.'
        'send_subscription_plan_expiration_emails.EnterpriseApiClient'
    )
    @override_settings(BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN='test-campaign-id')
    def test_subscription_plan_expiration_email_sent_date_not_set_on_failure(
        self, mock_enterprise_client, mock_create_braze_alias,
    ):
        """
        Test that subscription_plan_expiration_email_sent_date is NOT set when email fails to send.
        """
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.return_value = {
            'uuid': str(self.enterprise_customer_uuid),
            'slug': 'test-enterprise',
            'name': 'Test Enterprise',
            'contact_email': 'contact@example.com',
            'default_language': 'en',
        }

        # Mock Braze API to raise an exception
        mock_braze_instance = mock.Mock()
        mock_braze_instance.send_campaign_message.side_effect = BrazeClientError('Braze API error')
        mock_create_braze_alias.return_value = mock_braze_instance

        # Create license with subscription plan expired 3 days ago
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_ago=3,
            num_licenses=1
        )
        license_obj = licenses[0]

        # Verify subscription_plan_expiration_email_sent_date is initially None
        assert license_obj.subscription_plan_expiration_email_sent_date is None

        # Run the command - it should raise an exception
        with pytest.raises(Exception, match='subscription plan license expiration emails failed to send'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_since_expiration=7,
            )

        # Refresh license from database
        license_obj.refresh_from_db()

        # Verify subscription_plan_expiration_email_sent_date is still None (not set on failure)
        assert license_obj.subscription_plan_expiration_email_sent_date is None
