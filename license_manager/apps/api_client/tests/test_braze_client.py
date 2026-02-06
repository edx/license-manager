"""
Tests for the Braze API client.
"""
from unittest import mock

from braze.exceptions import BrazeClientError
from django.test import TestCase, override_settings

from license_manager.apps.api_client.braze import BrazeApiClient


class BrazeApiClientInitializationTests(TestCase):
    """
    Tests for BrazeApiClient initialization.
    """

    @override_settings(
        BRAZE_API_KEY='test-api-key',
        BRAZE_API_URL='https://rest.iad-01.braze.com',
        BRAZE_APP_ID='test-app-id'
    )
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.__init__', return_value=None)
    def test_initialization_success(self, mock_braze_client_init):
        """
        Verify that BrazeApiClient initializes successfully with required settings.
        """
        client = BrazeApiClient()

        # Verify that the parent BrazeClient was initialized with correct parameters
        mock_braze_client_init.assert_called_once_with(
            api_key='test-api-key',
            api_url='https://rest.iad-01.braze.com',
            app_id='test-app-id'
        )
        self.assertIsInstance(client, BrazeApiClient)

    @override_settings(BRAZE_API_KEY=None, BRAZE_API_URL='https://rest.iad-01.braze.com', BRAZE_APP_ID='test-app-id')
    def test_initialization_missing_api_key(self):
        """
        Verify that BrazeApiClient raises ValueError when BRAZE_API_KEY is missing.
        """
        with self.assertRaises(ValueError) as context:
            BrazeApiClient()

        self.assertIn('Missing BRAZE_API_KEY', str(context.exception))

    @override_settings(BRAZE_API_KEY='test-api-key', BRAZE_API_URL=None, BRAZE_APP_ID='test-app-id')
    def test_initialization_missing_api_url(self):
        """
        Verify that BrazeApiClient raises ValueError when BRAZE_API_URL is missing.
        """
        with self.assertRaises(ValueError) as context:
            BrazeApiClient()

        self.assertIn('Missing BRAZE_API_URL', str(context.exception))

    @override_settings(BRAZE_API_KEY='test-api-key', BRAZE_API_URL='https://rest.iad-01.braze.com', BRAZE_APP_ID=None)
    def test_initialization_missing_app_id(self):
        """
        Verify that BrazeApiClient raises ValueError when BRAZE_APP_ID is missing.
        """
        with self.assertRaises(ValueError) as context:
            BrazeApiClient()

        self.assertIn('Missing BRAZE_APP_ID', str(context.exception))

    @override_settings(BRAZE_API_KEY='', BRAZE_API_URL='https://rest.iad-01.braze.com', BRAZE_APP_ID='test-app-id')
    def test_initialization_empty_api_key(self):
        """
        Verify that BrazeApiClient raises ValueError when BRAZE_API_KEY is empty string.
        """
        with self.assertRaises(ValueError) as context:
            BrazeApiClient()

        self.assertIn('Missing BRAZE_API_KEY', str(context.exception))

    def test_initialization_settings_not_defined(self):
        """
        Verify that BrazeApiClient raises ValueError when settings are not defined at all.
        """
        # Remove all Braze-related settings if they exist
        with override_settings():
            # Delete the settings attributes to simulate them not being defined
            from django.conf import settings
            for attr in ['BRAZE_API_KEY', 'BRAZE_API_URL', 'BRAZE_APP_ID']:
                if hasattr(settings, attr):
                    delattr(settings, attr)

            with self.assertRaises(ValueError):
                BrazeApiClient()


class BrazeApiClientMethodTests(TestCase):
    """
    Tests for BrazeApiClient methods inherited from BrazeClient.
    """

    @override_settings(
        BRAZE_API_KEY='test-api-key',
        BRAZE_API_URL='https://rest.iad-01.braze.com',
        BRAZE_APP_ID='test-app-id'
    )
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.create_braze_alias')
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.__init__', return_value=None)
    def test_create_braze_alias_success(self, mock_braze_init, mock_create_alias):
        """
        Verify that create_braze_alias method works correctly.
        """
        client = BrazeApiClient()
        user_emails = ['user1@example.com', 'user2@example.com']
        alias_label = 'test-alias-label'

        mock_create_alias.return_value = {'aliases_processed': 2}

        result = client.create_braze_alias(user_emails, alias_label)

        mock_create_alias.assert_called_once_with(user_emails, alias_label)
        self.assertEqual(result, {'aliases_processed': 2})

    @override_settings(
        BRAZE_API_KEY='test-api-key',
        BRAZE_API_URL='https://rest.iad-01.braze.com',
        BRAZE_APP_ID='test-app-id'
    )
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.create_braze_alias')
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.__init__', return_value=None)
    def test_create_braze_alias_error(self, mock_braze_init, mock_create_alias):
        """
        Verify that create_braze_alias properly raises BrazeClientError on failure.
        """
        client = BrazeApiClient()
        user_emails = ['user1@example.com']
        alias_label = 'test-alias-label'

        mock_create_alias.side_effect = BrazeClientError('API Error')

        with self.assertRaises(BrazeClientError):
            client.create_braze_alias(user_emails, alias_label)

    @override_settings(
        BRAZE_API_KEY='test-api-key',
        BRAZE_API_URL='https://rest.iad-01.braze.com',
        BRAZE_APP_ID='test-app-id'
    )
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.send_campaign_message')
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.__init__', return_value=None)
    def test_send_campaign_message_success(self, mock_braze_init, mock_send_message):
        """
        Verify that send_campaign_message method works correctly.
        """
        client = BrazeApiClient()
        campaign_id = 'test-campaign-id'
        recipients = [
            {
                'external_user_id': '123',
                'trigger_properties': {'key': 'value'}
            }
        ]

        mock_send_message.return_value = {'message': 'success'}

        result = client.send_campaign_message(campaign_id, recipients=recipients)

        mock_send_message.assert_called_once_with(campaign_id, recipients=recipients)
        self.assertEqual(result, {'message': 'success'})

    @override_settings(
        BRAZE_API_KEY='test-api-key',
        BRAZE_API_URL='https://rest.iad-01.braze.com',
        BRAZE_APP_ID='test-app-id'
    )
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.send_campaign_message')
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.__init__', return_value=None)
    def test_send_campaign_message_error(self, mock_braze_init, mock_send_message):
        """
        Verify that send_campaign_message properly raises BrazeClientError on failure.
        """
        client = BrazeApiClient()
        campaign_id = 'test-campaign-id'
        recipients = [{'external_user_id': '123'}]

        mock_send_message.side_effect = BrazeClientError('Campaign not found')

        with self.assertRaises(BrazeClientError):
            client.send_campaign_message(campaign_id, recipients=recipients)

    @override_settings(
        BRAZE_API_KEY='test-api-key',
        BRAZE_API_URL='https://rest.iad-01.braze.com',
        BRAZE_APP_ID='test-app-id'
    )
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.send_campaign_message')
    @mock.patch('license_manager.apps.api_client.braze.BrazeClient.__init__', return_value=None)
    def test_send_campaign_message_with_trigger_properties(self, mock_braze_init, mock_send_message):
        """
        Verify that send_campaign_message handles trigger_properties correctly.
        """
        client = BrazeApiClient()
        campaign_id = 'test-campaign-id'
        recipients = [{'external_user_id': '123'}]
        trigger_properties = {
            'enterprise_customer_name': 'Test Enterprise',
            'subscription_plan_title': 'Test Plan'
        }

        mock_send_message.return_value = {'message': 'success'}

        result = client.send_campaign_message(
            campaign_id,
            recipients=recipients,
            trigger_properties=trigger_properties
        )

        mock_send_message.assert_called_once_with(
            campaign_id,
            recipients=recipients,
            trigger_properties=trigger_properties
        )
        self.assertEqual(result, {'message': 'success'})
