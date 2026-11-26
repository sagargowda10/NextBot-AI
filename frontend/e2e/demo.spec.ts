import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function ask(page: Page, text: string) {
  await page.getByLabel("Message").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Agents are working…")).toBeHidden({ timeout: 30_000 });
}

test("customer shops end-to-end through the AI assistant", async ({ page }) => {
  await login(page, "asha@nextbot.demo", "Demo@1234");
  await page.waitForURL("**/dashboard");
  await page.goto("/assistant");
  await expect(page.getByText(/Demo mode/)).toBeHidden(); // badge appears after first reply
  await ask(page, "Show me black running shoes in size 9.");
  await expect(page.getByText("Stridex Velocity Run").first()).toBeVisible();
  await expect(page.getByText(/Demo mode · mock AI/)).toBeVisible();
  await ask(page, "Add the first product to my cart.");
  await expect(page.getByText(/Added Stridex Velocity Run/)).toBeVisible();
  await ask(page, "Place my order.");
  await expect(page.getByText(/Payment of .* succeeded \(simulated/)).toBeVisible();
  await ask(page, "What is your return policy?");
  await expect(page.getByText(/10 days of delivery/)).toBeVisible();
  await expect(page.getByText(/Sources:/).last()).toBeVisible();
});

test("catalogue filters and cart", async ({ page }) => {
  await login(page, "rahul@nextbot.demo", "Demo@1234");
  await page.waitForURL("**/dashboard");
  await page.goto("/products");
  await page.getByLabel("Category").selectOption("audio");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("button", { name: /Add Auralis Buds ANC to cart/ }).click();
  await page.goto("/cart");
  await expect(page.getByText("Auralis Buds ANC")).toBeVisible();
});

test("admin sees 12 plugins and 12 agents", async ({ page }) => {
  await login(page, "admin@nextbot.demo", "Admin@1234");
  await page.waitForURL("**/admin");
  await page.goto("/admin/plugins");
  await expect(page.getByRole("button", { name: /Disable|Enable/ })).toHaveCount(12);
  await page.goto("/admin/agents");
  await expect(page.getByText("Supervisor Agent")).toBeVisible();
  await expect(page.getByText("Notification Agent")).toBeVisible();
});

test("catalogue lists products with no filters (page-size regression)", async ({ page }) => {
  await login(page, "rahul@nextbot.demo", "Demo@1234");
  await page.waitForURL("**/dashboard");
  await page.goto("/products");
  await expect(page.getByText(/^[1-9]\d* products$/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Add .* to cart/ }).first()).toBeVisible();
});

test("customer adds an address, checks out, admin delivers the order", async ({ page }) => {
  const label = `E2E ${Date.now()}`.slice(0, 40);
  await login(page, "meera@nextbot.demo", "Demo@1234");
  await page.waitForURL("**/dashboard");
  await page.goto("/addresses");
  await page.getByRole("button", { name: "+ Add address" }).click();
  await page.getByLabel("Label", { exact: true }).fill(label);
  await page.getByLabel("Phone").fill("9876543210");
  await page.getByLabel("Address line 1").fill("21 Test Street, Gokulam");
  await page.getByLabel("City").fill("Mysuru");
  await page.getByLabel("PIN code").fill("570002");
  await page.getByRole("button", { name: "Save address" }).click();
  await expect(page.getByText(label)).toBeVisible();

  await page.goto("/products");
  await page.getByRole("button", { name: /Add .* to cart/ }).first().click();
  await expect(page.getByText("Added ✓").first()).toBeVisible();
  await page.goto("/checkout");
  await page.getByText(label).click();
  await page.getByRole("button", { name: "Place order & pay" }).click();
  await page.waitForURL(/\/orders\/\d+/);
  const orderNumber = (await page.getByRole("heading", { level: 1 }).textContent())?.replace("Order ", "").trim() ?? "";

  await page.getByRole("button", { name: "Sign out" }).click();
  await login(page, "admin@nextbot.demo", "Admin@1234");
  await page.waitForURL("**/admin");
  await page.goto("/admin/orders");
  // The shipment is created by an event consumer just after payment, so retry until the courier step succeeds.
  const done = page.getByText(`${orderNumber} -> DELIVERED`);
  for (let attempt = 0; attempt < 10 && !(await done.isVisible()); attempt++) {
    const row = page.getByRole("row", { name: new RegExp(orderNumber) });
    await row.getByRole("button", { name: "Mark delivered" }).click({ timeout: 15_000 });
    await done.waitFor({ timeout: 2_000 }).catch(() => page.waitForTimeout(1_000));
  }
  await expect(done).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(orderNumber) }).getByText("DELIVERED", { exact: true })).toBeVisible();
});
