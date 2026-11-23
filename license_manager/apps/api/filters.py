"""
Filters for the License API.
"""

from django.db.models import Q
from django_filters import rest_framework as filters

from license_manager.apps.subscriptions.constants import (
    UNASSIGNED,
    LicenseActionSource,
    LicenseActionType,
    LicenseActorType,
)
from license_manager.apps.subscriptions.models import License, LicenseAction


class LicenseFilter(filters.FilterSet):
    """
    Filter for License.

    Supports filtering by license status and whether null emails are included.
    """
    status = filters.CharFilter(method='filter_by_status')
    ignore_null_emails = filters.BooleanFilter(method='filter_by_ignore_null_emails')

    class Meta:
        model = License
        fields = ['status']

    def filter_by_status(self, queryset, name, value):  # pylint: disable=unused-argument
        status_values = value.strip().split(',')
        return queryset.filter(status__in=status_values).distinct()

    # ignores revoked licenses that have been cleared of PII
    def filter_by_ignore_null_emails(self, queryset, name, value):  # pylint: disable=unused-argument
        if not value:
            return queryset
        return queryset.exclude(Q(user_email__isnull=True) & ~Q(status=UNASSIGNED))


class ChoiceInFilter(filters.BaseInFilter, filters.ChoiceFilter):
    """
    Accepts a comma-separated list of values, each of which must be one of the filter's choices.
    """


class LicenseActionFilter(filters.FilterSet):
    """
    Filter for LicenseAction audit records.

    Multi-valued filters take comma-separated values. Date bounds are inclusive and accept
    ISO-8601 dates or datetimes; values without an offset are interpreted as UTC.
    """
    action_type = ChoiceInFilter(choices=LicenseActionType.CHOICES)
    actor_type = ChoiceInFilter(choices=LicenseActorType.CHOICES)
    source = ChoiceInFilter(choices=LicenseActionSource.CHOICES)
    license_uuid = filters.UUIDFilter(field_name='license_id')
    learner_email = filters.CharFilter(lookup_expr='iexact')
    created_after = filters.DateTimeFilter(field_name='created', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='created', lookup_expr='lte')
    ordering = filters.ChoiceFilter(
        choices=(('-created', 'Newest first'), ('created', 'Oldest first')),
        method='order_by_created',
    )

    class Meta:
        model = LicenseAction
        fields = []

    def order_by_created(self, queryset, name, value):  # pylint: disable=unused-argument
        # uuid breaks ties between rows written in the same bulk operation, keeping pages stable.
        return queryset.order_by(value, value.replace('created', 'uuid'))
