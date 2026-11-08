import { expect, test } from '@playwright/test';

test('provider finds an uncovered high-need area and logs an activity there', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/areas$/);
  await expect(page.getByRole('heading', { name: 'Áreas de necesidad' })).toBeVisible();

  await page.getByRole('link', { name: 'Cobertura' }).click();
  const gaps = page.getByRole('region', { name: /sin cobertura con alta necesidad/ });
  const first = gaps.getByRole('listitem').first();
  const areaName = await first.getByRole('link').first().innerText();
  const logLink = first.getByRole('link', { name: 'Registrar actividad aquí' });
  const category = new URL((await logLink.getAttribute('href'))!, 'http://x').searchParams.get('category')!;
  const label = { water_drinking: 'Agua potable', water_other: 'Agua para otros usos', charging: 'Carga de dispositivos' }[
    category
  ]!;
  await logLink.click();

  await expect(page.getByRole('heading', { name: 'Registrar actividad' })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: new RegExp(areaName) })).toBeChecked();
  await expect(page.getByLabel('Categoría atendida')).toHaveValue(category);
  await page.getByRole('checkbox', { name: 'sáb' }).check();
  await page.getByRole('button', { name: 'Guardar actividad' }).click();

  await expect(page.getByText(/Actividad guardada/)).toBeVisible();
  await page.getByRole('link', { name: 'Cobertura' }).click();
  const row = page.getByRole('row').filter({ hasText: areaName }).filter({ hasText: label });
  await expect(row.getByText('Con cobertura')).toBeVisible();
  await expect(row.getByText('Agua Solidaria (sintético)')).toBeVisible();
});

test('area detail shows indicators, external context separately, and no horizontal scroll', async ({ page }) => {
  await page.goto('/areas/sec-acacias');
  await expect(page.getByRole('heading', { name: /Las Acacias/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Contexto externo' })).toBeVisible();
  await expect(page.getByText('Monitor Ciudad')).toBeVisible();
  for (const path of ['/areas', '/coverage', '/activities', '/activities/new', '/alerts', '/areas/sec-acacias']) {
    await page.goto(path);
    await page.getByRole('main').getByRole('heading').first().waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }
});

test('no persistent browser storage is written (WEB-060)', async ({ page }) => {
  await page.goto('/coverage');
  await expect(page.getByRole('table')).toBeVisible();
  const storage = await page.evaluate(async () => ({
    local: localStorage.length,
    session: sessionStorage.length,
    idb: (await indexedDB.databases()).length,
    sw: (await navigator.serviceWorker?.getRegistrations())?.length ?? 0,
  }));
  expect(storage).toEqual({ local: 0, session: 0, idb: 0, sw: 0 });
});
