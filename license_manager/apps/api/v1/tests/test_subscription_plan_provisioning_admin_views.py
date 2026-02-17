"""
Unit tests for SubscriptionPlanProvisioningAdminViewset.
"""
import json
from uuid import uuid4

import ddt
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from license_manager.apps.api.v1.tests.test_views import (
    _assign_role_via_jwt_or_db,
)
from license_manager.apps.subscriptions import constants
from license_manager.apps.subscriptions.tests.factories import (
    CustomerAgreementFactory,
    PlanTypeFactory,
    ProductFactory,
    SubscriptionPlanFactory,
    UserFactory,
)


@ddt.ddt
class SubscriptionPlanProvisioningAdminViewsetTests(APITestCase):
    """
    Tests for SubscriptionPlanProvisioningAdminViewset.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.user = UserFactory()
        self.staff_user = UserFactory(is_staff=True)
        self.enterprise_customer_uuid = uuid4()
        self.customer_agreement = CustomerAgreementFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid
        )
        ProductFactory.create_batch(1)

    def _setup_request_jwt(self, user=None):
        """
        Helper to set up JWT authentication for provisioning admin role.
        """
        if user is None:
            user = self.user
        _assign_role_via_jwt_or_db(
            self.client,
            user,
            enterprise_customer_uuid='*',
            assign_via_jwt=True,
            system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
        )

    def _get_list_url(self):
        """
        Helper to get the list URL with optional query parameters.
        """
        return reverse('api:v1:provisioning-admins-subscription-plans-list')

    def _get_detail_url(self, subscription_uuid, include_inactive=None):
        """
        Helper to get the detail URL with optional query parameters.
        """
        url = reverse(
            'api:v1:provisioning-admins-subscription-plans-detail',
            kwargs={'subscription_uuid': subscription_uuid}
        )
        if include_inactive is not None:
            url += f'?include_inactive={include_inactive}'
        return url

    @ddt.data(
        # Default behavior: only active plans visible
        {
            'include_inactive': None,
            'plan_is_active': False,
            'expected_found': False,
        },
        {
            'include_inactive': None,
            'plan_is_active': True,
            'expected_found': True,
        },
        # Explicit include_inactive=false: only active plans visible
        {
            'include_inactive': 'false',
            'plan_is_active': False,
            'expected_found': False,
        },
        {
            'include_inactive': 'false',
            'plan_is_active': True,
            'expected_found': True,
        },
        # include_inactive=true: both active and inactive plans visible
        {
            'include_inactive': 'true',
            'plan_is_active': False,
            'expected_found': True,
        },
        {
            'include_inactive': 'true',
            'plan_is_active': True,
            'expected_found': True,
        },
    )
    @ddt.unpack
    def test_include_inactive_parameter(self, include_inactive, plan_is_active, expected_found):
        """
        include_inactive query param should expose inactive SubscriptionPlan records for read/write.
        """
        self._setup_request_jwt()

        # Create a subscription plan with the specified active state
        subscription_plan = SubscriptionPlanFactory.create(
            customer_agreement=self.customer_agreement,
            is_active=plan_is_active,
            title=f'{"Active" if plan_is_active else "Inactive"} Test Plan'
        )

        # First, test the list endpoint.
        list_url = self._get_list_url()
        list_query_params = {"enterprise_customer_uuid": str(self.enterprise_customer_uuid)}
        if include_inactive:
            list_query_params["include_inactive"] = include_inactive

        response = self.client.get(list_url, query_params=list_query_params)

        assert response.status_code == status.HTTP_200_OK
        results = response.json()['results']
        found_uuids = [plan['uuid'] for plan in results]

        if expected_found:
            assert str(subscription_plan.uuid) in found_uuids
        else:
            assert str(subscription_plan.uuid) not in found_uuids

        # Next, test the update endpoint.
        update_url = self._get_detail_url(subscription_plan.uuid)
        update_data = {'title': 'Updated Title', 'change_reason': 'other'}
        update_query_params = {}
        if include_inactive is not None:
            update_query_params["include_inactive"] = include_inactive

        response = self.client.patch(
            update_url,
            data=json.dumps(update_data),
            query_params=update_query_params,
            content_type='application/json',
        )

        if expected_found:
            assert response.status_code == status.HTTP_200_OK
            assert response.json()['title'] == 'Updated Title'
            assert response.json()['is_active'] == plan_is_active
        else:
            assert response.status_code == status.HTTP_404_NOT_FOUND


################################################################################
# Legacy tests below which were unfortunately created outside of a test class. #
################################################################################

# Import test fixtures used by pytest test functions below.
# pylint: disable=unused-import, wrong-import-position
from .test_views import (  # noqa: E402
    api_client,
    boolean_toggle,
    non_staff_user,
    staff_user,
)


def _prepare_subscription_plan_payload(customer_agreement):
    return {
        "title": "foo",
        "start_date": "2024-04-29T15:17:53.462Z",
        "expiration_date": "2024-05-10T15:17:53.462Z",
        "enterprise_catalog_uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "is_active": True,
        "is_revocation_cap_enabled": False,
        "should_auto_apply_licenses": True,
        "can_freeze_unused_licenses": True,
        "customer_agreement": customer_agreement.uuid,
        "desired_num_licenses": 3,
        "expiration_processed": True,
        "for_internal_use_only": True,
        "last_freeze_timestamp": "2024-04-29T15:17:53.462Z",
        "num_revocations_applied": 10,
        "product": 1,
        "revoke_max_percentage": 5,
        "salesforce_opportunity_line_item": "00k2222asdfasdfasd",
        "change_reason": "new"
    }


# pylint: disable=redefined-outer-name
def _provision_license_create_request(api_client, user, params):
    """
    Helper method that creates a SubscriptionPlan.
    """
    if user:
        api_client.force_authenticate(user=user)

    url = '/api/v1/provisioning-admins/subscriptions'
    return api_client.post(url, params)


# pylint: disable=redefined-outer-name
def _provision_license_list_request(api_client, user, enterprise_customer_uuid=None):
    """
    Helper method that creates a SubscriptionPlan.
    """
    if user:
        api_client.force_authenticate(user=user)

    url = '/api/v1/provisioning-admins/subscriptions'
    if enterprise_customer_uuid:
        url += f'?enterprise_customer_uuid={enterprise_customer_uuid}'
    return api_client.get(url)


# pylint: disable=redefined-outer-name
def _provision_license_patch_request(api_client, user, params, subscription_uuid):
    """
    Helper method that updates a SubscriptionPlan.
    """
    if user:
        api_client.force_authenticate(user=user)

    url = f'/api/v1/provisioning-admins/subscriptions/{subscription_uuid}'
    return api_client.patch(url, params)


# pylint: disable=redefined-outer-name
def _subscription_get_request(api_client, user, subscription_uuid):
    """
    Helper method that creates a SubscriptionPlan.
    """
    if user:
        api_client.force_authenticate(user=user)

    url = f'/api/v1/provisioning-admins/subscriptions/{subscription_uuid}'
    return api_client.get(url)


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_200(api_client, non_staff_user):
    """
    Verify that the subscription POST endpoint creates new record and response includes all expected fields
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)
    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_201_CREATED == response.status_code
    expected_fields = {
        "can_freeze_unused_licenses",
        "change_reason",
        "customer_agreement",
        "days_until_expiration_including_renewals",
        "days_until_expiration",
        "desired_num_licenses",
        "enterprise_catalog_uuid",
        "enterprise_customer_uuid",
        "expiration_date",
        "expiration_processed",
        "for_internal_use_only",
        "is_active",
        "is_locked_for_renewal_processing",
        "is_revocation_cap_enabled",
        "last_freeze_timestamp",
        "num_revocations_applied",
        "product",
        "revoke_max_percentage",
        "salesforce_opportunity_line_item",
        "should_auto_apply_licenses",
        "start_date",
        "title",
        "uuid",
        "is_current",
        "created",
        "plan_type",
    }
    assert response.json().keys() == expected_fields


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_null_sf_oli(api_client, non_staff_user):
    """
    subcription creation for provisioning admins works even with a null SF opportunity line item.
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    # Make sure to create a PlanType that does not require salesforce IDs.
    plan_type = PlanTypeFactory.create(sf_id_required=False)
    ProductFactory(plan_type=plan_type)
    params = _prepare_subscription_plan_payload(customer_agreement)
    params['salesforce_opportunity_line_item'] = None
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_201_CREATED == response.status_code
    assert response.json()['salesforce_opportunity_line_item'] is None


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_staff_user_403(api_client, staff_user, boolean_toggle):
    """
    Verify that the subcription POST endpoint is accessible to authorised users only
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)
    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, staff_user, enterprise_customer_uuid=enterprise_customer_uuid, assign_via_jwt=boolean_toggle)

    response = _provision_license_create_request(
        api_client, staff_user, params=params)
    assert status.HTTP_403_FORBIDDEN == response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_list_staff_user_403(api_client, staff_user, boolean_toggle):
    """
    Verify that the subcription POST endpoint is accessible to authorised users only
    """
    enterprise_customer_uuid = uuid4()
    ProductFactory.create_batch(1)
    _assign_role_via_jwt_or_db(
        api_client, staff_user, enterprise_customer_uuid=enterprise_customer_uuid, assign_via_jwt=boolean_toggle)

    response = _provision_license_list_request(
        api_client, staff_user)
    assert status.HTTP_403_FORBIDDEN == response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_provisioning_admins_list_non_staff_user_200(api_client, non_staff_user):
    """
    Verify that the subcription POST endpoint is accessible to Provisioning Admins(non-staff) onlye
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )

    params = _prepare_subscription_plan_payload(customer_agreement)

    _provision_license_create_request(
        api_client, non_staff_user, params=params)

    response = _provision_license_list_request(
        api_client, non_staff_user)

    expected_keys = {'count', 'next', 'previous', 'results'}
    assert expected_keys.issubset(response.json().keys())
    expected_result_keys = {
        'title', 'uuid', 'start_date', 'expiration_date',
        'enterprise_customer_uuid', 'enterprise_catalog_uuid',
        'is_active', 'is_revocation_cap_enabled', 'days_until_expiration',
        'days_until_expiration_including_renewals',
        'is_locked_for_renewal_processing', 'should_auto_apply_licenses',
        'licenses', 'revocations', 'prior_renewals', 'created',
    }
    for result in response.json()['results']:
        assert expected_result_keys.issubset(result.keys())
    assert status.HTTP_200_OK == response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_pa_list_non_staff_user_200(api_client, non_staff_user):
    """
    Verify that the subcription POST endpoint applies enterprise_customer_uuid if passed
    in query params
    """
    # first create a subscription plan against a enterprise customer
    # then query it and test that customer uuid that's passed in query params
    # and the one received from `list` response are same.
    # We'll have to create two subscription plans to confirm it.

    enterprise_customer_uuid_one = uuid4()
    enterprise_customer_uuid_two = uuid4()
    customer_agreement_one = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid_one)
    customer_agreement_two = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid_two)
    ProductFactory.create_batch(1)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE
    )
    params_one = _prepare_subscription_plan_payload(customer_agreement_one)
    params_two = _prepare_subscription_plan_payload(customer_agreement_two)

    _provision_license_create_request(
        api_client, non_staff_user, params=params_one)

    response_one = _provision_license_list_request(
        api_client, non_staff_user, enterprise_customer_uuid=enterprise_customer_uuid_one)
    assert status.HTTP_200_OK == response_one.status_code
    assert response_one.json()['results'][0]['enterprise_customer_uuid'] == str(
        enterprise_customer_uuid_one)

    _provision_license_create_request(
        api_client, non_staff_user, params=params_two)
    response_two = _provision_license_list_request(
        api_client, non_staff_user, enterprise_customer_uuid=enterprise_customer_uuid_two)

    assert status.HTTP_200_OK == response_two.status_code
    assert response_two.json()['results'][0]['enterprise_customer_uuid'] == str(
        enterprise_customer_uuid_two)


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_update_staff_user_403(api_client, staff_user, boolean_toggle):
    """
    Verify that the subcription update endpoint is accessible to authorised users only
    """
    enterprise_customer_uuid = uuid4()
    fake_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)
    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, staff_user, enterprise_customer_uuid=enterprise_customer_uuid, assign_via_jwt=boolean_toggle)

    response = _provision_license_patch_request(
        api_client, staff_user, params=params, subscription_uuid=fake_uuid)

    assert status.HTTP_403_FORBIDDEN == response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_201(api_client, non_staff_user):
    """
    Verify that the subcription update endpoint is accessible to authorised users only
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)
    params = _prepare_subscription_plan_payload(customer_agreement)

    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _provision_license_create_request(
        api_client, non_staff_user, params=params)
    assert status.HTTP_201_CREATED == response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_customer_agreement_400(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid customer_agreement is given
    """
    enterprise_customer_uuid = uuid4()
    invalid_customer_agreement_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    params['customer_agreement'] = invalid_customer_agreement_uuid
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _provision_license_create_request(
        api_client, non_staff_user, params=params)
    assert status.HTTP_400_BAD_REQUEST == response.status_code
    assert response.json() == {'error': "An error occurred: Provided customer_agreement doesn't exist."}


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_product_400(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid Product is given
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    params['product'] = 2  # passing an invalid PK
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_400_BAD_REQUEST == response.status_code
    assert response.json() == {'error': {'product': [
        'Invalid pk "2" - object does not exist.']}}


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_salesforce_lineitem_400(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid salesforce_lineitem is given
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    # passing a invalid string
    params['salesforce_opportunity_line_item'] = 'foo'
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_400_BAD_REQUEST == response.status_code
    assert response.json() == \
        {'error': "An error occurred: Invalid Salesforce ID format. It must start with '00k'."}


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_update_non_staff_user_200(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns 200 on patch request
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)
    params['title'] = 'bar'
    patch_response = _provision_license_patch_request(
        api_client, non_staff_user, params=params, subscription_uuid=create_response.json()['uuid'])
    assert status.HTTP_201_CREATED == create_response.status_code
    assert status.HTTP_200_OK == patch_response.status_code
    expected_fields = {
        "can_freeze_unused_licenses",
        "change_reason",
        "customer_agreement",
        "days_until_expiration_including_renewals",
        "days_until_expiration",
        "desired_num_licenses",
        "enterprise_catalog_uuid",
        "enterprise_customer_uuid",
        "expiration_date",
        "expiration_processed",
        "for_internal_use_only",
        "is_active",
        "is_locked_for_renewal_processing",
        "is_revocation_cap_enabled",
        "last_freeze_timestamp",
        "num_revocations_applied",
        "product",
        "revoke_max_percentage",
        "salesforce_opportunity_line_item",
        "should_auto_apply_licenses",
        "start_date",
        "title",
        "uuid",
    }
    assert patch_response.json()['title'] == params['title']
    assert patch_response.json().keys() == expected_fields


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_update_non_staff_user_invalid_product_id(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns 200 on patch request
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)
    params['product'] = 10  # set invalid ID
    patch_response = _provision_license_patch_request(
        api_client, non_staff_user, params=params, subscription_uuid=create_response.json()['uuid'])
    assert status.HTTP_201_CREATED == create_response.status_code
    assert status.HTTP_400_BAD_REQUEST == patch_response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_update_non_staff_user_invalid_payload(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns 200 on patch request
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)
    params['salesforce_opportunity_line_item'] = 'foo'  # set invalid ID

    patch_response = _provision_license_patch_request(
        api_client, non_staff_user, params=params, subscription_uuid=create_response.json()['uuid'])
    assert status.HTTP_201_CREATED == create_response.status_code
    assert status.HTTP_400_BAD_REQUEST == patch_response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_cataog_uuid_missing(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint handles request gracefully if enterprise_catalog_uuid is missing
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    params['enterprise_catalog_uuid'] = None
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_201_CREATED == create_response.status_code

    assert create_response.json()['enterprise_catalog_uuid'] == str(
        customer_agreement.default_enterprise_catalog_uuid)


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_invalid_product_id(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid product id is provided
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    params['product'] = 12
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid='*', assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_400_BAD_REQUEST == create_response.status_code
    assert create_response.json(
    ) == {'error': {'product': ['Invalid pk "12" - object does not exist.']}}


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_create_non_staff_user_db_integrity_error(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid product id is provided
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid=None,
        assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    first_create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    second_create_response = _provision_license_create_request(
        api_client, non_staff_user, params=params)

    assert status.HTTP_201_CREATED == first_create_response.status_code
    assert status.HTTP_400_BAD_REQUEST == second_create_response.status_code
    assert second_create_response.json() == \
        {"error": {"non_field_errors": ["The fields title, customer_agreement must "
                                        "make a unique set."]}}


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_get_non_staff_user_success(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid product id is provided
    """
    enterprise_customer_uuid = uuid4()
    customer_agreement = CustomerAgreementFactory.create(
        enterprise_customer_uuid=enterprise_customer_uuid)
    ProductFactory.create_batch(1)

    params = _prepare_subscription_plan_payload(customer_agreement)
    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid=None,
        assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    create_response = _provision_license_create_request(
        api_client, non_staff_user, params)
    created_uuid = str(create_response.json()['uuid'])

    retrieved_subscription = _subscription_get_request(
        api_client, non_staff_user, created_uuid)

    assert retrieved_subscription.json()['uuid'] == created_uuid
    assert status.HTTP_201_CREATED == create_response.status_code


# pylint: disable=redefined-outer-name
@pytest.mark.django_db
def test_subscription_plan_get_non_staff_user_failure(api_client, non_staff_user):
    """
    Verify that the subscription create endpoint returns error if invalid product id is provided
    """
    invalid_subscription_id = uuid4()

    _assign_role_via_jwt_or_db(
        api_client, non_staff_user, enterprise_customer_uuid=None,
        assign_via_jwt=True,
        system_role=constants.SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE,
    )
    response = _subscription_get_request(
        api_client, non_staff_user, invalid_subscription_id)

    assert status.HTTP_404_NOT_FOUND == response.status_code
