import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockApiClient } from '../api';
import { FIXED_NOW, renderApp } from '../test/renderApp';

describe('app shell', () => {
  it('lands a provider on areas of need and shows org, provider and role (WEB-001/002)', async () => {
    const { router } = renderApp('/');
    await waitFor(() => expect(router.state.location.pathname).toBe('/areas'));
    expect(screen.getByText('Ciudadanía Sin Límites')).toBeInTheDocument();
    expect(screen.getByText('Agua Solidaria (sintético)')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' });
    expect(nav).toHaveTextContent('Mis actividades');
  });

  it('hides provider navigation from a coordinator', async () => {
    const client = new MockApiClient({ now: FIXED_NOW, latencyMs: 0 });
    client.setIdentity({ roles: ['coordinator'], vetting_status: 'vetted' });
    const { router } = renderApp('/', { client });
    await waitFor(() => expect(router.state.location.pathname).toBe('/data-health'));
    const nav = screen.getByRole('navigation', { name: 'Navegación principal' });
    expect(nav).not.toHaveTextContent('Mis actividades');
    expect(nav).toHaveTextContent('Cobertura');
  });

  it('shows the status banner when intake lags (WEB-007)', async () => {
    const client = new MockApiClient({ now: FIXED_NOW, latencyMs: 0 });
    client.setSimulatedStatus('intake_lag');
    renderApp('/areas', { client });
    expect(await screen.findByText(/se están procesando con retraso/)).toBeInTheDocument();
  });

  it('shows no banner when everything is normal', async () => {
    renderApp('/areas');
    await screen.findByRole('table');
    expect(screen.queryByText('Estado del servicio')).not.toBeInTheDocument();
  });

  it('"Salir" clears cached data and never writes browser storage (WEB-060/062)', async () => {
    const user = userEvent.setup();
    const { queryClient, router } = renderApp('/areas');
    await screen.findByRole('table');
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: 'Salir' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/signed-out'));
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
