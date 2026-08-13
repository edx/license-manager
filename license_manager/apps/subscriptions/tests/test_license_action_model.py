"""
Tests for the LicenseAction model (ENT-12031).
"""

from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase
from django.utils import timezone

from license_manager.apps.subscriptions.constants import (
    LicenseActionSource,
    LicenseActionType,
    LicenseActorType,
)
from license_manager.apps.subscriptions.models import LicenseAction
from license_manager.apps.subscriptions.tests.factories import (
    CustomerAgreementFactory,
    LicenseFactory,
    SubscriptionPlanFactory,
)


class TestLicenseActionModel(TestCase):
    """
    Tests for the LicenseAction audit model.
    """

    def setUp(self):
        self.customer_agreement = CustomerAgreementFactory()
        self.subscription_plan = SubscriptionPlanFactory(
            customer_agreement=self.customer_agreement,
        )
        self.license = LicenseFactory(
            subscription_plan=self.subscription_plan,
        )
        self.enterprise_customer_uuid = self.customer_agreement.enterprise_customer_uuid

    def _create_action(self, **kwargs):
        """
        Helper to create a LicenseAction with defaults.
        """
        defaults = {
            "license": self.license,
            "subscription_plan": self.subscription_plan,
            "enterprise_customer_uuid": self.enterprise_customer_uuid,
            "action_type": LicenseActionType.ASSIGNED,
            "actor_type": LicenseActorType.ADMIN,
            "source": LicenseActionSource.ADMIN_UI,
        }
        defaults.update(kwargs)
        return LicenseAction.objects.create(**defaults)

    # =========================================================
    # Model creation tests
    # =========================================================

    def test_create_with_required_fields_only(self):
        """
        LicenseAction can be created with only required fields.
        """
        action = self._create_action()
        self.assertIsNotNone(action.uuid)
        self.assertIsNotNone(action.created)
        self.assertIsNotNone(action.modified)
        self.assertEqual(action.license, self.license)
        self.assertEqual(action.subscription_plan, self.subscription_plan)
        self.assertEqual(action.enterprise_customer_uuid, self.enterprise_customer_uuid)
        self.assertEqual(action.action_type, LicenseActionType.ASSIGNED)
        self.assertEqual(action.actor_type, LicenseActorType.ADMIN)
        self.assertEqual(action.source, LicenseActionSource.ADMIN_UI)

    def test_create_with_all_fields(self):
        """
        LicenseAction can be created with all fields populated.
        """
        action = self._create_action(
            actor_lms_user_id=42,
            learner_lms_user_id=99,
            learner_email="learner@example.com",
            learner_external_key="ext-key-123",
            correlation_id="corr-abc-456",
            metadata={"reason": "bulk_upload", "batch_id": 7},
        )
        self.assertEqual(action.actor_lms_user_id, 42)
        self.assertEqual(action.learner_lms_user_id, 99)
        self.assertEqual(action.learner_email, "learner@example.com")
        self.assertEqual(action.learner_external_key, "ext-key-123")
        self.assertEqual(action.correlation_id, "corr-abc-456")
        self.assertEqual(action.metadata, {"reason": "bulk_upload", "batch_id": 7})

    def test_uuid_is_auto_generated(self):
        """
        UUID primary key is automatically generated.
        """
        action = self._create_action()
        self.assertIsNotNone(action.uuid)
        # Verify it's a valid UUID by checking it's not equal to a new one
        self.assertNotEqual(action.uuid, uuid4())

    # =========================================================
    # Nullable field tests
    # =========================================================

    def test_nullable_fields_accept_none(self):
        """
        All nullable fields accept None without error.
        """
        action = self._create_action()
        self.assertIsNone(action.actor_lms_user_id)
        self.assertIsNone(action.learner_lms_user_id)
        self.assertIsNone(action.learner_email)
        self.assertIsNone(action.learner_external_key)
        self.assertIsNone(action.correlation_id)

    def test_metadata_defaults_to_empty_dict(self):
        """
        metadata field defaults to an empty dict.
        """
        action = self._create_action()
        self.assertEqual(action.metadata, {})

    # =========================================================
    # Enum / choices tests
    # =========================================================

    def test_all_action_type_values(self):
        """
        All action_type enum values can be stored.
        """
        for choice_value, _ in LicenseActionType.CHOICES:
            action = self._create_action(action_type=choice_value)
            self.assertEqual(action.action_type, choice_value)

    def test_all_actor_type_values(self):
        """
        All actor_type enum values can be stored.
        """
        for choice_value, _ in LicenseActorType.CHOICES:
            action = self._create_action(actor_type=choice_value)
            self.assertEqual(action.actor_type, choice_value)

    def test_all_source_values(self):
        """
        All source enum values can be stored.
        """
        for choice_value, _ in LicenseActionSource.CHOICES:
            action = self._create_action(source=choice_value)
            self.assertEqual(action.source, choice_value)

    def test_action_type_has_eight_choices(self):
        """
        LicenseActionType has exactly 8 choices.
        """
        self.assertEqual(len(LicenseActionType.CHOICES), 8)

    def test_actor_type_has_three_choices(self):
        """
        LicenseActorType has exactly 3 choices.
        """
        self.assertEqual(len(LicenseActorType.CHOICES), 3)

    def test_source_has_six_choices(self):
        """
        LicenseActionSource has exactly 6 choices.
        """
        self.assertEqual(len(LicenseActionSource.CHOICES), 6)

    # =========================================================
    # FK relationship tests
    # =========================================================

    def test_related_name_on_license(self):
        """
        License.actions related_name works correctly.
        """
        action = self._create_action()
        self.assertIn(action, self.license.actions.all())

    def test_related_name_on_subscription_plan(self):
        """
        SubscriptionPlan.license_actions related_name works correctly.
        """
        action = self._create_action()
        self.assertIn(action, self.subscription_plan.license_actions.all())

    def test_license_fk_uses_do_nothing(self):
        """
        LicenseAction.license uses DO_NOTHING to preserve audit history.
        """
        remote_field = LicenseAction._meta.get_field("license").remote_field
        self.assertEqual(remote_field.on_delete, models.DO_NOTHING)

    def test_subscription_plan_fk_uses_do_nothing(self):
        """
        LicenseAction.subscription_plan uses DO_NOTHING to preserve audit history.
        """
        remote_field = LicenseAction._meta.get_field("subscription_plan").remote_field
        self.assertEqual(remote_field.on_delete, models.DO_NOTHING)

    def test_license_fk_disables_db_constraint(self):
        """
        LicenseAction.license disables DB constraint for audit row retention.
        """
        field = LicenseAction._meta.get_field("license")
        self.assertFalse(field.db_constraint)

    def test_subscription_plan_fk_disables_db_constraint(self):
        """
        LicenseAction.subscription_plan disables DB constraint for audit row retention.
        """
        field = LicenseAction._meta.get_field("subscription_plan")
        self.assertFalse(field.db_constraint)

    def test_clean_rejects_mismatched_subscription_plan(self):
        """
        Validation fails when subscription_plan does not match license.subscription_plan.
        """
        other_plan = SubscriptionPlanFactory(customer_agreement=self.customer_agreement)
        action = LicenseAction(
            license=self.license,
            subscription_plan=other_plan,
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            action_type=LicenseActionType.ASSIGNED,
            actor_type=LicenseActorType.ADMIN,
            source=LicenseActionSource.ADMIN_UI,
        )

        with self.assertRaises(ValidationError) as context:
            action.full_clean()
        self.assertIn("subscription_plan", context.exception.message_dict)

    def test_clean_rejects_mismatched_enterprise_customer_uuid(self):
        """
        Validation fails when enterprise_customer_uuid does not match linked license.
        """
        other_agreement = CustomerAgreementFactory()
        action = LicenseAction(
            license=self.license,
            subscription_plan=self.subscription_plan,
            enterprise_customer_uuid=other_agreement.enterprise_customer_uuid,
            action_type=LicenseActionType.ASSIGNED,
            actor_type=LicenseActorType.ADMIN,
            source=LicenseActionSource.ADMIN_UI,
        )

        with self.assertRaises(ValidationError) as context:
            action.full_clean()
        self.assertIn("enterprise_customer_uuid", context.exception.message_dict)

    def test_clean_allows_missing_enterprise_customer_uuid(self):
        """
        clean() skips enterprise-customer consistency check when value is missing.
        """
        action = LicenseAction(
            license=self.license,
            subscription_plan=self.subscription_plan,
            enterprise_customer_uuid=None,
            action_type=LicenseActionType.ASSIGNED,
            actor_type=LicenseActorType.ADMIN,
            source=LicenseActionSource.ADMIN_UI,
        )
        action.clean()

    def test_clean_allows_missing_foreign_keys(self):
        """
        clean() safely no-ops when foreign keys are unset on an unsaved instance.
        """
        action = LicenseAction(
            enterprise_customer_uuid=None,
            action_type=LicenseActionType.ASSIGNED,
            actor_type=LicenseActorType.ADMIN,
            source=LicenseActionSource.ADMIN_UI,
        )
        action.clean()

    # =========================================================
    # Ordering tests
    # =========================================================

    def test_ordering_is_descending_created(self):
        """
        Test that LicenseAction records are ordered by descending creation time.
        """
        now = timezone.now()
        action_1 = self._create_action(created=now - timedelta(seconds=2))
        action_2 = self._create_action(created=now - timedelta(seconds=1))
        action_3 = self._create_action(created=now)
        actions = list(LicenseAction.objects.all())
        self.assertEqual(actions, [action_3, action_2, action_1])

    # =========================================================
    # Index tests
    # =========================================================

    def test_model_has_expected_indexes(self):
        """
        LicenseAction Meta defines 3 composite indexes.
        """
        index_names = [index.name for index in LicenseAction._meta.indexes]
        self.assertIn("idx_licaction_license_created", index_names)
        self.assertIn("idx_licaction_entcust_created", index_names)
        self.assertIn("idx_licaction_subplan_created", index_names)

    def test_has_three_indexes(self):
        """
        Exactly 3 indexes are defined in Meta.
        """
        self.assertEqual(len(LicenseAction._meta.indexes), 3)

    # =========================================================
    # __str__ tests
    # =========================================================

    def test_str_representation(self):
        """
        __str__ includes action_type and actor_type.
        """
        action = self._create_action(
            action_type=LicenseActionType.REVOKED,
            actor_type=LicenseActorType.SYSTEM,
        )
        str_repr = str(action)
        self.assertIn("revoked", str_repr)
        self.assertIn("system", str_repr)

    # =========================================================
    # Multiple actions per license
    # =========================================================

    def test_multiple_actions_on_same_license(self):
        """
        A single license can have multiple LicenseActions.
        """
        self._create_action(action_type=LicenseActionType.ASSIGNED)
        self._create_action(action_type=LicenseActionType.ACTIVATED)
        self._create_action(action_type=LicenseActionType.REVOKED)
        self.assertEqual(self.license.actions.count(), 3)

    # =========================================================
    # No regression on existing License model
    # =========================================================

    def test_existing_license_model_unaffected(self):
        """
        Adding LicenseAction does not break existing License functionality.
        """
        # License can still be created, saved, and queried
        new_license = LicenseFactory(subscription_plan=self.subscription_plan)
        self.assertIsNotNone(new_license.uuid)
        self.assertEqual(new_license.subscription_plan, self.subscription_plan)
        # Existing relationships still work
        self.assertIn(new_license, self.subscription_plan.licenses.all())
