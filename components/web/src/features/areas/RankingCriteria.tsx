import type { RankingCriterion } from '../../api';
import { useI18n } from '../../locales/i18n';
import { commonStyles } from '../../ui/common';

/** DOM-043: the ordering is declared, versioned, and shown. No hidden weights. */
export function RankingCriteria({ criteria, methodVersion }: { criteria: RankingCriterion[]; methodVersion: string }) {
  const { t } = useI18n();
  return (
    <section className={commonStyles.notice} aria-labelledby="ranking-criteria">
      <h2 id="ranking-criteria" style={{ margin: '0 0 0.25rem', fontSize: '1rem' }}>
        {t('ranking.title')}
      </h2>
      <ol style={{ margin: '0 0 0.25rem', paddingLeft: '1.3rem' }}>
        {criteria.map((c) => (
          <li key={c.key}>
            {t(`ranking.criterion.${c.key}`)} <span className="muted">({t(`ranking.direction.${c.key}`)})</span>
          </li>
        ))}
      </ol>
      <span className="muted" style={{ fontSize: '0.85rem' }}>
        {t('ranking.method', { version: methodVersion })} · {t('ranking.noHiddenWeights')}
      </span>
    </section>
  );
}
