"""
Management command to send subscription plan expiration emails to learners.

This command identifies activated licenses whose subscription plans have recently expired
and sends notification emails via Braze.
"""
import logging
import re
import uuid
from datetime import timedelta

from braze.exceptions import BrazeClientError
from django.conf import settings
from django.core.management.base import BaseCommand

from license_manager.apps.api import utils as api_utils
from license_manager.apps.api_client.enterprise import EnterpriseApiClient
from license_manager.apps.subscriptions.constants import (
    ACTIVATED,
    BRAZE_TIMESTAMP_FORMAT,
    ENTERPRISE_BRAZE_ALIAS_LABEL,
)
from license_manager.apps.subscriptions.models import License
from license_manager.apps.subscriptions.utils import (
    get_enterprise_sender_alias,
    localized_utcnow,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to send subscription plan expiration emails.

    Example usage:
        # Send emails for a specific enterprise customer (plans expired in last 7 days)
        ./manage.py send_subscription_plan_expiration_emails --enterprise-customer-uuid 12345678-1234-1234-1234-123456789012

        # Send emails for multiple enterprise customers, separated by either commas or spaces
        ./manage.py send_subscription_plan_expiration_emails --enterprise-customer-uuid "uuid1,uuid2,uuid3"

        # Send emails with custom days threshold
        ./manage.py send_subscription_plan_expiration_emails --enterprise-customer-uuid 12345678-1234-1234-1234-123456789012 --days-since-expiration 14

        # Dry run to see which licenses would be processed, without sending emails
        ./manage.py send_subscription_plan_expiration_emails --enterprise-customer-uuid 12345678-1234-1234-1234-123456789012 --dry-run
    """

    help = (
        'Sends Braze emails to learners with activated licenses whose subscription plans have recently expired.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--enterprise-customer-uuid',
            action='store',
            dest='enterprise_customer_uuid',
            type=str,
            required=True,
            help=(
                'UUID(s) of enterprise customer(s) to send expiration emails for. '
                'Can be a single UUID or multiple UUIDs separated by commas or spaces.'
            ),
        )
        parser.add_argument(
            '--days-since-expiration',
            action='store',
            dest='days_since_expiration',
            type=int,
            default=7,
            help=(
                'Number of days to look back from today, excluding today, when selecting expired plans (default: 7).'
                'Processes subscription plans that expired within the last N full calendar days.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='If set, only log which licenses would be processed without sending emails.'
        )

    def _parse_enterprise_customer_uuids(self, uuids_string: str) -> list[str]:
        """
        Parse a string containing one or more enterprise customer UUIDs.

        Args:
            uuids_string (str): String containing UUIDs separated by commas, spaces, or both

        Returns:
            list: List of stripped UUID strings
        """
        # Split by commas and/or whitespace
        uuids = re.split(r'[,\s]+', uuids_string.strip())
        # Filter out empty strings
        uuids = [_uuid.strip() for _uuid in uuids if _uuid.strip()]
        # Parse each string as a UUID to verify they're syntactically correct
        for item in uuids:
            try:
                uuid.UUID(item)
            except ValueError:
                logger.error('%s is not a valid UUID', item)
                raise
        return uuids

    def _get_recently_expired_plan_licenses(self, enterprise_customer_uuid, days_since_expiration):
        """
        Get activated licenses whose subscription plans have recently expired.

        Only returns licenses that have not yet received an expiration email.
        This allows the cron to run more frequently without sending duplicate emails.

        Args:
            enterprise_customer_uuid (str): UUID of the enterprise customer
            days_since_expiration (int): Number of days since expiration

        Returns:
            QuerySet of License objects
        """
        now = localized_utcnow()
        # Find subscription plans that expired within the last N days, **EXCLUDING TODAY**
        # This ensures we only process confirmed past expirations, not today's expirations
        expiration_window_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        expiration_window_start = expiration_window_end - timedelta(days=days_since_expiration)

        licenses = License.objects.filter(
            status=ACTIVATED,
            subscription_plan__customer_agreement__enterprise_customer_uuid=enterprise_customer_uuid,
            subscription_plan__expiration_date__gte=expiration_window_start,
            subscription_plan__expiration_date__lt=expiration_window_end,
            # Only send to licenses that haven't received email yet
            subscription_plan_expiration_email_sent_date__isnull=True,
        ).select_related(
            'subscription_plan',
            'subscription_plan__customer_agreement'
        )

        return licenses

    def _send_subscription_expiration_email(self, license_obj, enterprise_customer):
        """
        Send subscription plan expiration email for a single license via Braze.

        Args:
            license_obj (License): The license to send email for
            enterprise_customer (dict): Enterprise customer data from API

        Raises:
            BrazeClientError: If Braze API call fails
        """
        user_email = license_obj.user_email
        enterprise_slug = enterprise_customer.get('slug')
        enterprise_name = enterprise_customer.get('name')
        enterprise_sender_alias = get_enterprise_sender_alias(enterprise_customer)
        enterprise_contact_email = enterprise_customer.get('contact_email')
        enterprise_default_language = enterprise_customer.get('default_language') or ''

        expiration_date = license_obj.subscription_plan.expiration_date
        delta = localized_utcnow().date() - expiration_date.date()
        days_since_expiration = delta.days

        # Prepare Braze campaign trigger properties
        trigger_properties = {
            'enterprise_customer_slug': enterprise_slug,
            'enterprise_customer_name': enterprise_name,
            'enterprise_sender_alias': enterprise_sender_alias,
            'enterprise_contact_email': enterprise_contact_email,
            'expiration_date': expiration_date.strftime(BRAZE_TIMESTAMP_FORMAT),
            'days_since_expiration': days_since_expiration,
            'subscription_plan_title': license_obj.subscription_plan.title,
        }

        # Prepare recipient object
        recipient = {
            'attributes': {
                'email': user_email,
                'enterprise_default_language': enterprise_default_language,
            },
            'user_alias': {
                'alias_label': ENTERPRISE_BRAZE_ALIAS_LABEL,
                'alias_name': user_email,
            },
        }

        # Get Braze campaign ID from settings
        braze_campaign_id = getattr(settings, 'BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN', None)
        if not braze_campaign_id:
            raise ValueError(
                'BRAZE_SUBSCRIPTION_PLAN_EXPIRATION_CAMPAIGN setting is not configured. '
                'Please set this to the Braze campaign ID for subscription plan expiration emails.'
            )

        # Send email via Braze
        braze_client = api_utils.create_braze_alias_for_emails([user_email])
        braze_client.send_campaign_message(
            braze_campaign_id,
            recipients=[recipient],
            trigger_properties=trigger_properties,
        )

        logger.info(
            f'Sent subscription plan expiration email to {user_email} for license {license_obj.uuid} '
            f'with plan expired on {expiration_date.strftime(BRAZE_TIMESTAMP_FORMAT)}'
        )

    def _process_enterprise_customer(self, enterprise_customer_uuid, days_since_expiration, dry_run):
        """
        Process subscription plan expiration emails for a single enterprise customer.

        Args:
            enterprise_customer_uuid (str): UUID of the enterprise customer
            days_since_expiration (int): Number of days since expiration to process
            dry_run (bool): If True, only log which licenses would be processed

        Returns:
            dict: Dictionary with 'success_count' and 'failure_count' keys
        """
        logger.info(
            f'Processing enterprise {enterprise_customer_uuid}, '
            f'days_since_expiration={days_since_expiration}, dry_run={dry_run}'
        )

        # Get licenses with recently expired subscription plans
        licenses = self._get_recently_expired_plan_licenses(enterprise_customer_uuid, days_since_expiration)

        if not licenses.exists():
            logger.info(
                f'No activated licenses found with subscription plans expired in the last {days_since_expiration} days '
                f'for enterprise {enterprise_customer_uuid}'
            )
            return {'success_count': 0, 'failure_count': 0}

        logger.info(f'Found {licenses.count()} licenses to process for enterprise {enterprise_customer_uuid}')

        if dry_run:
            logger.info(f'DRY RUN - Would send subscription plan expiration emails for enterprise {enterprise_customer_uuid}:')
            for license_obj in licenses:
                logger.info(
                    f'  License UUID: {license_obj.uuid}, '
                    f'User Email: {license_obj.user_email}, '
                    f'Expiration Date: {license_obj.subscription_plan.expiration_date.strftime("%Y-%m-%d")}'
                )
            return {'success_count': 0, 'failure_count': 0}

        # Get enterprise customer data from API
        try:
            enterprise_api_client = EnterpriseApiClient()
            enterprise_customer = enterprise_api_client.get_enterprise_customer_data(enterprise_customer_uuid)
        except Exception as exc:
            logger.exception(
                f'Failed to get enterprise customer data for {enterprise_customer_uuid}: {exc}'
            )
            raise

        # Send emails for each license
        success_count = 0
        failure_count = 0

        for license_obj in licenses:
            try:
                self._send_subscription_expiration_email(license_obj, enterprise_customer)
                # Mark the license as having received a subscription plan expiration email
                license_obj.subscription_plan_expiration_email_sent_date = localized_utcnow()
                license_obj.save(update_fields=['subscription_plan_expiration_email_sent_date'])
                success_count += 1
            except ValueError as exc:
                raise
            except BrazeClientError as exc:
                logger.exception(
                    f'Failed to send subscription plan expiration email for license {license_obj.uuid}: {exc}'
                )
                failure_count += 1
            except Exception as exc:
                logger.exception(
                    f'Unexpected error sending subscription plan expiration email for license {license_obj.uuid}: {exc}'
                )
                failure_count += 1

        logger.info(
            f'Completed processing for enterprise {enterprise_customer_uuid}. '
            f'Success: {success_count}, Failures: {failure_count}'
        )

        return {'success_count': success_count, 'failure_count': failure_count}

    def handle(self, *args, **options):
        """
        Main command handler.
        """
        enterprise_customer_uuids_string = options['enterprise_customer_uuid']
        days_since_expiration = options['days_since_expiration']
        dry_run = options['dry_run']

        # Parse the enterprise customer UUIDs
        enterprise_customer_uuids = self._parse_enterprise_customer_uuids(enterprise_customer_uuids_string)

        if not enterprise_customer_uuids:
            logger.error('No valid enterprise customer UUIDs provided')
            raise ValueError('No valid enterprise customer UUIDs provided')

        logger.info(
            f'Starting send_subscription_plan_expiration_emails command for {len(enterprise_customer_uuids)} '
            f'enterprise customer(s), days_since_expiration={days_since_expiration}, dry_run={dry_run}'
        )

        # Process each enterprise customer
        total_success_count = 0
        total_failure_count = 0
        enterprise_level_failures = 0

        for enterprise_customer_uuid in enterprise_customer_uuids:
            try:
                result = self._process_enterprise_customer(
                    enterprise_customer_uuid,
                    days_since_expiration,
                    dry_run
                )
                total_success_count += result['success_count']
                total_failure_count += result['failure_count']
            except ValueError as exc:
                # Configuration error - re-raise immediately
                raise
            except Exception as exc:
                logger.exception(
                    f'Failed to process enterprise customer {enterprise_customer_uuid}: {exc}'
                )
                # Continue processing other enterprise customers
                enterprise_level_failures += 1

        logger.info(
            f'Completed send_subscription_plan_expiration_emails command for {len(enterprise_customer_uuids)} '
            f'enterprise customer(s). Total Success: {total_success_count}, Total Failures: {total_failure_count}'
        )

        if (total_failure_count + enterprise_level_failures) > 0:
            raise Exception(
                f'{enterprise_level_failures} enterprise customers could not be processed'
                f'{total_failure_count} subscription plan license expiration emails failed to send '
                f'across {len(enterprise_customer_uuids)} enterprise customer(s)'
            )
