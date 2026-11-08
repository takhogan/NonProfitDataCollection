import type { ActivitySummary } from '../../api';
import { useI18n } from '../../locales/i18n';

export function ActivityChip({ activity }: { activity: ActivitySummary }) {
  const { t } = useI18n();
  return (
    <span>
      <strong>{activity.provider_organization.name}</strong> —{' '}
      {activity.details_hidden ? (
        <span className="muted">{t('activity.detailsHidden')}</span>
      ) : (
        t(`activityType.${activity.type}`)
      )}{' '}
      <span className="muted">({t(`activityStatus.${activity.status}`)})</span>
    </span>
  );
}
