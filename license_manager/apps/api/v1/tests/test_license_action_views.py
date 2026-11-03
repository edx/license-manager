"""
Tests for the subscription audit-history endpoint backed by ``LicenseActionViewSet``.
"""
from datetime import timedelta
from uuid import uuid4

import ddt
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from license_manager.apps.api.serializers import LicenseActionSerializer
from license_manager.apps.api.v1.tests.test_views import (
    _assign_role_via_jwt_or_db,
)
from license_manager.apps.subscriptions import constants
from license_manager.apps.subscriptions.constants import (
    LicenseActionSource,
    LicenseActionType,
    LicenseActorType,
)
from license_manager.apps.subscriptions.models import License, LicenseAction
from license_manager.apps.subscriptions.tests.factories import (
    CustomerAgreementFactory,
    LicenseFactory,
    SubscriptionPlanFactory,
    UserFactory,
)


@ddt.ddt
class LicenseActionViewSetTests(APITestCase):
    """
    Tests for ``GET /api/v1/subscriptions/{subscription_uuid}/audit-history/``.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.enterprise_customer_uuid = uuid4()
        cls.plan = SubscriptionPlanFactory(
            customer_agreement=CustomerAgreementFactory(enterprise_customer_uuid=cls.enterprise_customer_uuid),
        )
        cls.other_plan = SubscriptionPlanFactory()
        cls.admin_user = UserFactory(email='admin@example.com', full_name='Admin User')
        cls.license_1 = LicenseFactory(
            subscription_plan=cls.plan, status=constants.ACTIVATED, user_email='learner1@example.com',
        )
        cls.license_2 = LicenseFactory(
            subscription_plan=cls.plan, status=constants.REVOKED, user_email='learner2@example.com',
        )
        now = timezone.now()
        cls.assigned_action = cls._create_action(
            cls.license_1,
            created=now - timedelta(days=3),
            action_type=LicenseActionType.ASSIGNED,
            actor_type=LicenseActorType.ADMIN,
            actor_lms_user_id=cls.admin_user.id,
            source=LicenseActionSource.ADMIN_API_BULK,
            correlation_id='batch-1',
            metadata={'batch_size': 2, 'requested_email_count': 2, 'learner_external_key': 'sf-123'},
        )
        cls.revoked_action = cls._create_action(
            cls.license_2,
            created=now - timedelta(days=2),
            action_type=LicenseActionType.REVOKED,
            actor_type=LicenseActorType.ADMIN,
            actor_lms_user_id=cls.admin_user.id,
            source=LicenseActionSource.ADMIN_API,
            metadata={'original_status': constants.ASSIGNED, 'idempotency_key': 'abc:def:revoked'},
        )
        cls.renewed_action = cls._create_action(
            cls.license_1,
            created=now - timedelta(days=1),
            action_type=LicenseActionType.RENEWED,
            actor_type=LicenseActorType.SYSTEM,
            source=LicenseActionSource.RENEWAL_JOB,
            metadata={'is_auto_renewed': True, 'renewal_id': 7},
        )
        cls.other_customer_action = cls._create_action(
            LicenseFactory(subscription_plan=cls.other_plan, user_email='other@example.com'),
            action_type=LicenseActionType.ASSIGNED,
            actor_type=LicenseActorType.ADMIN,
            source=LicenseActionSource.ADMIN_API_BULK,
        )

    @staticmethod
    def _create_action(license_obj, **kwargs):
        return LicenseAction.objects.create(
            license=license_obj,
            subscription_plan=license_obj.subscription_plan,
            enterprise_customer_uuid=license_obj.subscription_plan.enterprise_customer_uuid,
            learner_email=license_obj.user_email,
            **kwargs,
        )

    def _url(self, subscription_uuid=None):
        return reverse(
            'api:v1:audit-history-list',
            kwargs={'subscription_uuid': subscription_uuid or self.plan.uuid},
        )

    def _get_as_admin(self, params=None, subscription_uuid=None):
        _assign_role_via_jwt_or_db(self.client, self.admin_user, self.enterprise_customer_uuid, assign_via_jwt=True)
        return self.client.get(self._url(subscription_uuid), params or {})

    def _result_uuids(self, response):
        return [result['uuid'] for result in response.json()['results']]

    def test_list_returns_plan_history_newest_first(self):
        response = self._get_as_admin()

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['count'] == 3
        assert self._result_uuids(response) == [
            str(self.renewed_action.uuid),
            str(self.revoked_action.uuid),
            str(self.assigned_action.uuid),
        ]

    def test_response_structure(self):
        response = self._get_as_admin({'action_type': LicenseActionType.ASSIGNED})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['num_pages'] == 1
        assert response.json()['results'] == [{
            'uuid': str(self.assigned_action.uuid),
            'created': self.assigned_action.created.isoformat().replace('+00:00', 'Z'),
            'action_type': LicenseActionType.ASSIGNED,
            'actor_type': LicenseActorType.ADMIN,
            'actor': {'email': 'admin@example.com', 'full_name': 'Admin User'},
            'source': LicenseActionSource.ADMIN_API_BULK,
            'license_uuid': str(self.license_1.uuid),
            'learner_email': 'learner1@example.com',
            'correlation_id': 'batch-1',
            'metadata': {'batch_size': 2, 'requested_email_count': 2},
        }]

    def test_empty_history(self):
        empty_plan = SubscriptionPlanFactory(customer_agreement=self.plan.customer_agreement)

        response = self._get_as_admin(subscription_uuid=empty_plan.uuid)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['count'] == 0
        assert response.json()['results'] == []

    def test_other_customers_actions_are_never_returned(self):
        response = self._get_as_admin()

        assert str(self.other_customer_action.uuid) not in self._result_uuids(response)

    def test_history_of_deleted_license_is_preserved(self):
        deleted_license_uuid = self.license_2.uuid
        License.objects.filter(uuid=deleted_license_uuid).delete()

        response = self._get_as_admin({'action_type': LicenseActionType.REVOKED})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['results'][0]['license_uuid'] == str(deleted_license_uuid)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self._url())

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @ddt.data(
        # Admin of a different enterprise customer.
        {'role': constants.SYSTEM_ENTERPRISE_ADMIN_ROLE, 'other_customer': True},
        # Learner of the plan's enterprise customer.
        {'role': constants.SYSTEM_ENTERPRISE_LEARNER_ROLE, 'other_customer': False},
        # Authenticated, without any role.
        {'role': None, 'other_customer': False},
    )
    @ddt.unpack
    def test_unauthorized_users_are_forbidden(self, role, other_customer):
        enterprise_customer_uuid = uuid4() if other_customer else self.enterprise_customer_uuid
        _assign_role_via_jwt_or_db(
            self.client, UserFactory(), enterprise_customer_uuid, assign_via_jwt=True, system_role=role,
        )

        response = self.client.get(self._url())

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_role_assigned_via_database_is_authorized(self):
        _assign_role_via_jwt_or_db(self.client, UserFactory(), self.enterprise_customer_uuid, assign_via_jwt=False)

        response = self.client.get(self._url())

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['count'] == 3

    def test_operator_with_all_access_is_authorized(self):
        _assign_role_via_jwt_or_db(
            self.client, UserFactory(), '*', assign_via_jwt=True, system_role=constants.SYSTEM_ENTERPRISE_OPERATOR_ROLE,
        )

        response = self.client.get(self._url())

        assert response.status_code == status.HTTP_200_OK

    @ddt.data(uuid4(), 'not-a-uuid')
    def test_missing_or_invalid_subscription_returns_404(self, subscription_uuid):
        response = self._get_as_admin(subscription_uuid=subscription_uuid)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_pagination(self):
        first_page = self._get_as_admin({'page_size': 2})
        second_page = self._get_as_admin({'page_size': 2, 'page': 2})

        assert first_page.json()['count'] == 3
        assert first_page.json()['num_pages'] == 2
        assert first_page.json()['next'] is not None
        assert self._result_uuids(first_page) + self._result_uuids(second_page) == [
            str(self.renewed_action.uuid),
            str(self.revoked_action.uuid),
            str(self.assigned_action.uuid),
        ]

    @ddt.data(
        ({'action_type': 'assigned'}, ['assigned_action']),
        ({'action_type': 'assigned,revoked'}, ['revoked_action', 'assigned_action']),
        ({'actor_type': 'system'}, ['renewed_action']),
        ({'source': 'admin_api,renewal_job'}, ['renewed_action', 'revoked_action']),
        ({'learner_email': 'LEARNER1@example.com'}, ['renewed_action', 'assigned_action']),
        ({'ordering': 'created'}, ['assigned_action', 'revoked_action', 'renewed_action']),
    )
    @ddt.unpack
    def test_filters(self, params, expected_actions):
        response = self._get_as_admin(params)

        assert response.status_code == status.HTTP_200_OK
        assert self._result_uuids(response) == [str(getattr(self, name).uuid) for name in expected_actions]

    def test_filter_by_license_uuid(self):
        response = self._get_as_admin({'license_uuid': str(self.license_2.uuid)})

        assert self._result_uuids(response) == [str(self.revoked_action.uuid)]

    def test_filter_by_date_range(self):
        response = self._get_as_admin({
            'created_after': (self.revoked_action.created - timedelta(hours=1)).isoformat(),
            'created_before': (self.revoked_action.created + timedelta(hours=1)).isoformat(),
        })

        assert self._result_uuids(response) == [str(self.revoked_action.uuid)]

    @ddt.data(
        {'action_type': 'not_an_action'},
        {'action_type': 'assigned,not_an_action'},
        {'actor_type': 'robot'},
        {'source': 'carrier_pigeon'},
        {'license_uuid': 'not-a-uuid'},
        {'created_after': 'yesterday'},
        {'ordering': 'learner_email'},
    )
    def test_invalid_filters_return_400(self, params):
        response = self._get_as_admin(params)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.json()) == set(params)

    @ddt.data('-created', 'created')
    def test_ordering_is_stable_for_actions_with_equal_timestamps(self, ordering):
        created = timezone.now() - timedelta(days=10)
        same_time_actions = [
            self._create_action(
                self.license_1,
                created=created,
                action_type=LicenseActionType.ASSIGNED,
                actor_type=LicenseActorType.ADMIN,
                source=LicenseActionSource.ADMIN_API_BULK,
            )
            for _ in range(3)
        ]
        expected = sorted((str(action.uuid) for action in same_time_actions), reverse=ordering.startswith('-'))

        response = self._get_as_admin({'ordering': ordering, 'created_before': created.isoformat()})

        assert self._result_uuids(response) == expected

    def test_actor_is_null_for_system_and_missing_users(self):
        missing_actor_action = self._create_action(
            self.license_1,
            action_type=LicenseActionType.REVOKED,
            actor_type=LicenseActorType.ADMIN,
            actor_lms_user_id=self.admin_user.id + 1000,
            source=LicenseActionSource.ADMIN_API,
        )

        results = {result['uuid']: result for result in self._get_as_admin().json()['results']}

        assert results[str(self.renewed_action.uuid)]['actor'] is None
        assert results[str(missing_actor_action.uuid)]['actor'] is None

    def test_actor_falls_back_to_first_and_last_name(self):
        named_user = UserFactory(email='named@example.com', full_name=None, first_name='Ada', last_name='Admin')
        action = self._create_action(
            self.license_1,
            action_type=LicenseActionType.REVOKED,
            actor_type=LicenseActorType.ADMIN,
            actor_lms_user_id=named_user.id,
            source=LicenseActionSource.ADMIN_API,
        )

        data = LicenseActionSerializer([action], many=True).data

        assert data[0]['actor'] == {'email': 'named@example.com', 'full_name': 'Ada Admin'}

    def test_actors_are_resolved_with_a_single_query(self):
        for _ in range(3):
            self._create_action(
                self.license_1,
                action_type=LicenseActionType.REVOKED,
                actor_type=LicenseActorType.ADMIN,
                actor_lms_user_id=UserFactory().id,
                source=LicenseActionSource.ADMIN_API,
            )

        # One query for the actions, one for all of their actors.
        with self.assertNumQueries(2):
            data = LicenseActionSerializer(LicenseAction.objects.filter(subscription_plan=self.plan), many=True).data

        assert len(data) == 6

    def test_metadata_is_limited_to_allowlisted_keys(self):
        results = {result['uuid']: result for result in self._get_as_admin().json()['results']}

        assert results[str(self.assigned_action.uuid)]['metadata'] == {'batch_size': 2, 'requested_email_count': 2}
        assert results[str(self.revoked_action.uuid)]['metadata'] == {'original_status': constants.ASSIGNED}
        assert results[str(self.renewed_action.uuid)]['metadata'] == {'is_auto_renewed': True}
