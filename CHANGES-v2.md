# NextBot AI — v2 fixes

## 1. Products page showed "0 products" (fixed)
`/products` called `/api/v1/products/search?size=24`. The backend used `size` for BOTH page size and the
shoe/clothing size filter, so it searched for products in "size 24" → nothing matched.
- Backend `app/api/v1/catalog.py`: product size filter is now `variant_size`; `size` = page size only.
- Frontend `app/products/page.tsx`: the Size box sends `variant_size`.

## 2. Addresses (new)
- Sidebar → **Addresses** (`/addresses`): add, edit, delete, set default.
- **Checkout** now has "+ Add new address" inline; if you have none, the form shows automatically.
- Backend `app/api/v1/auth.py`: added `PUT /me/addresses/{id}`, `DELETE /me/addresses/{id}`,
  `POST /me/addresses/{id}/default`; first address becomes default automatically; only one default;
  duplicate label returns a clear 409 message.
- New component `components/AddressForm.tsx` (PIN 6 digits, phone 10–13 digits, Indian states list).

## 3. Landing page
Top-rated products now appear on the home page (`components/FeaturedProducts.tsx`).

## Apply
docker compose -f docker-compose.dev.yml up --build
(The frontend must be rebuilt — NEXT_PUBLIC_API_URL is baked in at build time. No DB reset needed.)

## Demo flow to test
Products → Add to cart → Cart → Proceed to checkout → Add address → Place order & pay → Orders (track) → Returns.

## v3
- Admin **All Orders** page (`/admin/orders`): list every order, simulate the courier (Next step / Mark delivered).
- Tests: `tests/integration/test_api_addresses.py` (new), catalogue page-size regression, 2 new Playwright specs.
- `scripts/verify.ps1`: runs every backend/frontend/E2E check on Windows and saves results to `docs/test-results-local.md`.
