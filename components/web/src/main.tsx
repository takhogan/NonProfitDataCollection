import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { createProductClient } from './api/product';
import { createQueryClient, ProductProviders } from './product/AppProviders';
import { productRoutes } from './product/routes';
import './ui/global.css';

// Metron product app. The legacy provider-portal pages (src/app, src/features)
// remain in the tree but are no longer mounted; see src/product for the
// hackathon product. Swap mock → real backend with VITE_API_MODE/VITE_API_BASE_URL.
const router = createBrowserRouter(productRoutes);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProductProviders client={createProductClient()} queryClient={createQueryClient()}>
      <RouterProvider router={router} />
    </ProductProviders>
  </StrictMode>,
);
