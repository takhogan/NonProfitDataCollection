/**
 * DEVELOPMENT ONLY. Switches the mock identity and simulates failures. Never
 * rendered in production builds (see Layout.tsx) or with the real API.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { MockApiClient, type DevIdentity, type SimulatedStatus } from '../../api';
import { useApi } from '../../api/context';
import s from './DevRoleSwitcher.module.css';

const PRESETS: Record<string, DevIdentity> = {
  'provider (vetted)': { roles: ['provider'], vetting_status: 'vetted' },
  'provider (unvetted)': { roles: ['provider'], vetting_status: 'unvetted' },
  coordinator: { roles: ['coordinator'], vetting_status: 'vetted' },
  reviewer: { roles: ['reviewer'], vetting_status: 'vetted' },
  intake_volunteer: { roles: ['intake_volunteer'], vetting_status: 'vetted' },
  analyst: { roles: ['analyst'], vetting_status: 'vetted' },
  org_admin: { roles: ['org_admin'], vetting_status: 'vetted' },
  'coordinator + provider': { roles: ['coordinator', 'provider'], vetting_status: 'vetted' },
};

export default function DevRoleSwitcher() {
  const api = useApi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [preset, setPreset] = useState('provider (vetted)');
  const [status, setStatus] = useState<SimulatedStatus>('normal');
  const [armed, setArmed] = useState(false);
  if (!(api instanceof MockApiClient)) return null;

  return (
    <aside className={s.bar} aria-label="Developer controls (not in production)" lang="en">
      <strong>DEV ONLY</strong>
      <label>
        Role
        <select
          value={preset}
          onChange={(e) => {
            setPreset(e.target.value);
            api.setIdentity(PRESETS[e.target.value]!);
            // Same as an org/role change in production: drop every cache.
            qc.clear();
            navigate('/', { replace: true });
          }}
        >
          {Object.keys(PRESETS).map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </label>
      <label>
        Status
        <select
          value={status}
          onChange={(e) => {
            const v = e.target.value as SimulatedStatus;
            setStatus(v);
            api.setSimulatedStatus(v);
            qc.invalidateQueries({ predicate: (q) => q.queryKey[1] === 'status' });
          }}
        >
          <option value="normal">normal</option>
          <option value="intake_lag">intake lag</option>
          <option value="degraded">degraded</option>
        </select>
      </label>
      <button
        type="button"
        onClick={() => {
          api.failNextWrite('network_error');
          setArmed(true);
        }}
      >
        {armed ? 'Next save will fail' : 'Fail next save'}
      </button>
    </aside>
  );
}
