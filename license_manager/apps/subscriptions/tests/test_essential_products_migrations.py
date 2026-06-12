from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


ACADEMY_PRODUCT_NAMES = [
    'SSP Essentials AI Academy',
    'SSP Essentials Sustainability Academy',
    'SSP Essentials Tech and Digital Academy',
    'SSP Essentials Data Academy',
    'SSP Essentials Management Academy',
    'SSP Essentials Leadership Academy',
    'SSP Essentials Supply Chain Academy',
    'SSP Essentials Communication Academy',
]


class MigrationTestCase(TransactionTestCase):
    """
    Base migration test helper that migrates from one state to another.
    """

    migrate_from = None
    migrate_to = None

    def setUp(self):
        super().setUp()

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_from])

        old_state = executor.loader.project_state([self.migrate_from])
        self.old_apps = old_state.apps
        self.setUpBeforeMigration(self.old_apps)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def setUpBeforeMigration(self, apps):
        pass


class PopulateEssentialsAcademyProductsMigrationTests(MigrationTestCase):
    migrate_from = ('subscriptions', '0081_remove_unique_netsuite_id')
    migrate_to = ('subscriptions', '0082_add_all_academies_subscription_plan')

    def setUpBeforeMigration(self, apps):
        PlanType = apps.get_model('subscriptions', 'PlanType')
        Product = apps.get_model('subscriptions', 'Product')

        self.trials_plan_type = PlanType.objects.create(
            label='self-service-trial',
            description='Self-service trial plans',
            is_paid_subscription=False,
            ns_id_required=False,
            sf_id_required=False,
            internal_use_only=False,
        )

        self.non_trials_plan_type = PlanType.objects.create(
            label='standard-paid',
            description='Standard paid plans',
            is_paid_subscription=True,
            ns_id_required=True,
            sf_id_required=True,
            internal_use_only=False,
        )

        # This existing product should be preserved and not duplicated.
        Product.objects.create(
            name='SSP Essentials AI Academy',
            description='Existing description',
            plan_type_id=self.trials_plan_type.id,
        )

    def test_populates_essentials_products_for_trial_plan_types(self):
        PlanType = self.apps.get_model('subscriptions', 'PlanType')
        Product = self.apps.get_model('subscriptions', 'Product')

        trials_plan_type = PlanType.objects.get(label='self-service-trial')
        products = Product.objects.filter(
            plan_type_id=trials_plan_type.id,
            name__in=ACADEMY_PRODUCT_NAMES,
        )

        self.assertEqual(products.count(), len(ACADEMY_PRODUCT_NAMES))
        self.assertEqual(set(products.values_list('name', flat=True)), set(ACADEMY_PRODUCT_NAMES))

    def test_does_not_duplicate_existing_products(self):
        PlanType = self.apps.get_model('subscriptions', 'PlanType')
        Product = self.apps.get_model('subscriptions', 'Product')

        trials_plan_type = PlanType.objects.get(label='self-service-trial')
        ai_academy_products = Product.objects.filter(
            plan_type_id=trials_plan_type.id,
            name='SSP Essentials AI Academy',
        )

        self.assertEqual(ai_academy_products.count(), 1)
        self.assertEqual(ai_academy_products.get().description, 'Existing description')

    def test_does_not_populate_for_non_target_plan_types(self):
        PlanType = self.apps.get_model('subscriptions', 'PlanType')
        Product = self.apps.get_model('subscriptions', 'Product')

        non_trials_plan_type = PlanType.objects.get(label='standard-paid')
        products = Product.objects.filter(
            plan_type_id=non_trials_plan_type.id,
            name__in=ACADEMY_PRODUCT_NAMES,
        )

        self.assertEqual(products.count(), 0)
