"""
Tests for the send_license_expiration_reminders management command.
"""
from datetime import timedelta
from unittest import mock
from uuid import uuid4

import pytest
from braze.exceptions import BrazeClientError
from django.core.management import call_command
from django.test import TestCase, override_settings

from license_manager.apps.subscriptions.constants import ACTIVATED, ASSIGNED, REVOKED
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


@pytest.mark.django_db
class SendLicenseExpirationRemindersTests(TestCase):
    """
    Tests for the send_license_expiration_reminders management command.
    """
    command_name = 'send_license_expiration_reminders'

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

    def _create_subscription_with_licenses(self, expiration_days_from_now, num_licenses=1, license_status=ACTIVATED):
        """
        Helper to create a subscription plan with licenses.

        Args:
            expiration_days_from_now (int): Number of days from now when the subscription expires
            num_licenses (int): Number of licenses to create
            license_status (str): Status of the licenses to create

        Returns:
            tuple: (SubscriptionPlan, list of Licenses)
        """
        now = localized_utcnow()
        expiration_date = now + timedelta(days=expiration_days_from_now)

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
        Test that the command handles the case when no expiring licenses are found.
        """
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )
            assert any('No activated licenses found' in msg for msg in log.output)

    def test_dry_run_mode(self):
        """
        Test that dry run mode logs licenses without sending emails.
        """
        # Create a license expiring in 30 days
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=2
        )

        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
                dry_run=True,
            )

            # Verify dry run messages
            assert any('DRY RUN' in msg for msg in log.output)
            assert any(str(licenses[0].uuid) in msg for msg in log.output)
            assert any(str(licenses[1].uuid) in msg for msg in log.output)

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_send_reminders_success(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test successful sending of expiration reminder emails.
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

        # Create licenses expiring in 30 days
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=2
        )

        # Run command
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )

            # Verify success messages
            assert any('Success: 2' in msg for msg in log.output)

        # Verify Braze API was called correctly
        assert mock_create_braze_alias.call_count == 2
        assert mock_braze_instance.send_campaign_message.call_count == 2

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
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

        # Create licenses with different statuses, all expiring in 30 days
        now = localized_utcnow()
        expiration_date = now + timedelta(days=30)

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
                days_before_expiration=30,
            )

            # Verify only 1 license was processed (the activated one)
            assert any('Success: 1' in msg for msg in log.output)

        # Verify only one email was sent
        assert mock_braze_instance.send_campaign_message.call_count == 1

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_custom_days_before_expiration(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that custom days_before_expiration parameter works correctly.
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

        # Create licenses expiring in 60 days
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=60,
            num_licenses=1
        )

        # Run command with 60 days
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=60,
            )

            # Verify success
            assert any('Success: 1' in msg for msg in log.output)

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
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
            expiration_days_from_now=30,
            num_licenses=1
        )

        # Run command - should raise exception due to failures
        with pytest.raises(Exception, match='1 license expiration reminder emails failed to send'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
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
            expiration_days_from_now=30,
            num_licenses=2
        )

        # Create licenses for a different enterprise
        different_enterprise_uuid = uuid4()
        different_customer_agreement = CustomerAgreementFactory(
            enterprise_customer_uuid=different_enterprise_uuid
        )
        now = localized_utcnow()
        expiration_date = now + timedelta(days=30)
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
                days_before_expiration=30,
            )

            # Verify only 2 licenses were processed (not the one from the different enterprise)
            assert any('Success: 2' in msg for msg in log.output)

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN=None)
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
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
            expiration_days_from_now=30,
            num_licenses=1
        )

        # Run command - should raise ValueError
        with pytest.raises(ValueError, match='BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN setting is not configured'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    def test_enterprise_api_error_handling(self, mock_enterprise_client):
        """
        Test that Enterprise API errors are handled properly.
        """
        # Make Enterprise API raise an error
        mock_enterprise_instance = mock_enterprise_client.return_value
        mock_enterprise_instance.get_enterprise_customer_data.side_effect = Exception('Enterprise API error')

        # Create licenses
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=1
        )

        # Enterprise API errors should cause the command to fail with an exception
        with pytest.raises(Exception, match='1 license expiration reminder emails failed to send'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_multiple_enterprise_customers_comma_separated(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that the command can process multiple enterprise customers separated by commas.
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
            expiration_days_from_now=30,
            num_licenses=2
        )

        # Create licenses for second enterprise (3 licenses)
        now = localized_utcnow()
        expiration_date = now + timedelta(days=30)
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
                enterprise_customer_uuid=f'{self.enterprise_customer_uuid},{second_enterprise_uuid}',
                days_before_expiration=30,
            )

            # Verify both enterprises were processed
            assert any('2 enterprise customer(s)' in msg for msg in log.output)
            assert any('Total Success: 5' in msg for msg in log.output)

        # Verify Braze API was called for all 5 licenses
        assert mock_create_braze_alias.call_count == 5
        assert mock_braze_instance.send_campaign_message.call_count == 5

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_multiple_enterprise_customers_space_separated(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that the command can process multiple enterprise customers separated by spaces.
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

        # Create licenses for first enterprise (1 license)
        subscription_plan1, licenses1 = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=1
        )

        # Create licenses for second enterprise (2 licenses)
        now = localized_utcnow()
        expiration_date = now + timedelta(days=30)
        subscription_plan2 = SubscriptionPlanFactory(
            customer_agreement=second_customer_agreement,
            start_date=now - timedelta(days=365),
            expiration_date=expiration_date,
            is_active=True,
        )
        for _ in range(2):
            LicenseFactory(
                subscription_plan=subscription_plan2,
                status=ACTIVATED,
                user_email=f'user{uuid4()}@example.com',
                lms_user_id=12345,
            )

        # Run command with space-separated UUIDs
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=f'{self.enterprise_customer_uuid} {second_enterprise_uuid}',
                days_before_expiration=30,
            )

            # Verify both enterprises were processed
            assert any('2 enterprise customer(s)' in msg for msg in log.output)
            assert any('Total Success: 3' in msg for msg in log.output)

        # Verify Braze API was called for all 3 licenses
        assert mock_create_braze_alias.call_count == 3
        assert mock_braze_instance.send_campaign_message.call_count == 3

    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    def test_multiple_enterprise_customers_one_has_no_licenses(self, mock_create_braze_alias, mock_enterprise_client):
        """
        Test that the command continues processing when one enterprise has no expiring licenses.
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
            expiration_days_from_now=30,
            num_licenses=2
        )

        # Second enterprise has no expiring licenses

        # Run command with both UUIDs
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=f'{self.enterprise_customer_uuid},{second_enterprise_uuid}',
                days_before_expiration=30,
            )

            # Verify both enterprises were processed
            assert any('2 enterprise customer(s)' in msg for msg in log.output)
            assert any('Total Success: 2' in msg for msg in log.output)
            assert any(f'No activated licenses found' in msg for msg in log.output)

        # Verify Braze API was called only for first enterprise's 2 licenses
        assert mock_create_braze_alias.call_count == 2
        assert mock_braze_instance.send_campaign_message.call_count == 2

    def test_empty_enterprise_customer_uuids(self):
        """
        Test that the command raises an error when no UUIDs are provided.
        """
        with pytest.raises(ValueError, match='No valid enterprise customer UUIDs provided'):
            call_command(
                self.command_name,
                enterprise_customer_uuid='   ',
                days_before_expiration=30,
            )

    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    def test_expiration_reminder_sent_date_set_on_success(self, mock_enterprise_client, mock_create_braze_alias):
        """
        Test that expiration_reminder_sent_date is set when email is successfully sent.
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

        # Create license expiring in 30 days
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=1
        )
        license_obj = licenses[0]

        # Verify expiration_reminder_sent_date is initially None
        assert license_obj.expiration_reminder_sent_date is None

        # Run the command
        call_command(
            self.command_name,
            enterprise_customer_uuid=str(self.enterprise_customer_uuid),
            days_before_expiration=30,
        )

        # Refresh license from database
        license_obj.refresh_from_db()

        # Verify expiration_reminder_sent_date is now set
        assert license_obj.expiration_reminder_sent_date is not None

    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    def test_licenses_with_reminder_already_sent_are_skipped(self, mock_enterprise_client, mock_create_braze_alias):
        """
        Test that licenses that already have expiration_reminder_sent_date set are skipped.
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

        # Create 3 licenses expiring in 30 days
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=3
        )

        # Mark first license as already having received a reminder
        now = localized_utcnow()
        licenses[0].expiration_reminder_sent_date = now - timedelta(days=1)
        licenses[0].save()

        # Run the command
        with self.assertLogs(level='INFO') as log:
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )

            # Should only find 2 licenses (the ones without expiration_reminder_sent_date)
            assert any('Found 2 licenses to process' in msg for msg in log.output)

        # Verify Braze API was called only for the 2 licenses without the reminder
        assert mock_create_braze_alias.call_count == 2
        assert mock_braze_instance.send_campaign_message.call_count == 2

    @mock.patch('license_manager.apps.api.utils.create_braze_alias_for_emails')
    @mock.patch('license_manager.apps.subscriptions.management.commands.send_license_expiration_reminders.EnterpriseApiClient')
    @override_settings(BRAZE_LICENSE_EXPIRATION_REMINDER_CAMPAIGN='test-campaign-id')
    def test_expiration_reminder_sent_date_not_set_on_failure(self, mock_enterprise_client, mock_create_braze_alias):
        """
        Test that expiration_reminder_sent_date is NOT set when email fails to send.
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

        # Create license expiring in 30 days
        subscription_plan, licenses = self._create_subscription_with_licenses(
            expiration_days_from_now=30,
            num_licenses=1
        )
        license_obj = licenses[0]

        # Verify expiration_reminder_sent_date is initially None
        assert license_obj.expiration_reminder_sent_date is None

        # Run the command - it should raise an exception
        with pytest.raises(Exception, match='license expiration reminder emails failed to send'):
            call_command(
                self.command_name,
                enterprise_customer_uuid=str(self.enterprise_customer_uuid),
                days_before_expiration=30,
            )

        # Refresh license from database
        license_obj.refresh_from_db()

        # Verify expiration_reminder_sent_date is still None (not set on failure)
        assert license_obj.expiration_reminder_sent_date is None
