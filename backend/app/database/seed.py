"""Idempotent, realistic *fictional* seed data. Run: `python -m app.database.seed` (also runs on startup in demo mode)."""

from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrderStatus, PaymentStatus, Role, ShipmentStatus
from app.domain.pricing import LineInput, calculate_totals
from app.models.ai import KnowledgeDocument
from app.models.catalog import Brand, Coupon, Product, ProductCategory, ProductImage, ProductVariant, Review
from app.models.commerce import Order, OrderItem, Payment, Shipment, ShoppingCart
from app.models.inventory import Inventory, Warehouse
from app.models.user import Address, CustomerProfile, Permission, User
from app.models.user import Role as RoleModel
from app.rag.pipeline import load_markdown_docs
from app.security.passwords import hash_password
from app.security.permissions import ROLE_PERMISSIONS

DEMO_USERS = [
    # email, password, name, phone, roles, address (label, line1, city, state, pincode), budget hints
    (
        "asha@nextbot.demo",
        "Demo@1234",
        "Asha Rao",
        "+919800000001",
        [Role.CUSTOMER],
        ("Home", "12 Temple Road, VV Mohalla", "Mysuru", "Karnataka", "570002"),
        {"smartphones": 25000, "laptops": 60000},
    ),
    (
        "rahul@nextbot.demo",
        "Demo@1234",
        "Rahul Menon",
        "+919800000002",
        [Role.CUSTOMER],
        ("Home", "44 4th Cross, Koramangala", "Bengaluru", "Karnataka", "560034"),
        {"audio": 6000},
    ),
    (
        "meera@nextbot.demo",
        "Demo@1234",
        "Meera Shah",
        "+919800000003",
        [Role.CUSTOMER],
        ("Office", "7 Nehru Place", "New Delhi", "Delhi", "110019"),
        {},
    ),
    ("admin@nextbot.demo", "Admin@1234", "Nisha Admin", "+919800000009", [Role.ADMIN], None, {}),
    ("support@nextbot.demo", "Support@1234", "Sam Support", "+919800000008", [Role.SUPPORT_AGENT], None, {}),
    ("inventory@nextbot.demo", "Inventory@1234", "Ivan Inventory", "+919800000007", [Role.INVENTORY_MANAGER], None, {}),
]

BRANDS = ["Voltix", "Nimbus", "Auralis", "Stridex", "HearthCo"]
CATEGORIES = [
    ("Laptops", "laptops"),
    ("Smartphones", "smartphones"),
    ("Audio", "audio"),
    ("Footwear", "footwear"),
    ("Apparel", "apparel"),
    ("Wearables", "wearables"),
    ("Home & Kitchen", "home-kitchen"),
]

# name, brand, category, price, mrp, rating, tags, description, specs, variants [(size, colour, qty_blr, qty_mys)]
PRODUCTS: list[tuple[Any, ...]] = [
    (
        "Voltix AirBook 14",
        "Voltix",
        "laptops",
        54990,
        64990,
        4.4,
        "thin light office student",
        "A 1.3 kg aluminium laptop with all-day battery for work and study.",
        {
            "Processor": "Ryzen 5 7530U",
            "RAM": "16 GB",
            "Storage": "512 GB SSD",
            "Display": '14" FHD IPS',
            "Battery": "12 h",
            "Weight": "1.3 kg",
        },
        [(None, "silver", 14, 0), (None, "grey", 3, 0)],
    ),
    (
        "Nimbus Pro 15",
        "Nimbus",
        "laptops",
        58990,
        69990,
        4.2,
        "office gaming creator",
        '15.6" performance laptop with a dedicated GPU for light gaming and editing.',
        {
            "Processor": "Core i5-13420H",
            "RAM": "16 GB",
            "Storage": "512 GB SSD",
            "GPU": "RTX 3050",
            "Display": '15.6" 144 Hz',
            "Weight": "1.9 kg",
        },
        [(None, "black", 6, 0)],
    ),
    (
        "Nimbus Ultra 16",
        "Nimbus",
        "laptops",
        89990,
        104990,
        4.7,
        "gaming creator premium",
        'Creator-class laptop with a 16" 2.5K display and RTX 4060.',
        {
            "Processor": "Core i7-13700H",
            "RAM": "32 GB",
            "Storage": "1 TB SSD",
            "GPU": "RTX 4060",
            "Display": '16" 2.5K 165 Hz',
            "Weight": "2.2 kg",
        },
        [(None, "black", 4, 0)],
    ),
    (
        "Voltix Chromebook Go",
        "Voltix",
        "laptops",
        24990,
        29990,
        3.9,
        "student budget",
        "Affordable Chromebook for browsing, classes and documents.",
        {"Processor": "MediaTek Kompanio 520", "RAM": "8 GB", "Storage": "128 GB eMMC", "Display": '11.6" HD', "Weight": "1.1 kg"},
        [(None, "blue", 20, 0)],
    ),
    (
        "Nimbus Note 5G",
        "Nimbus",
        "smartphones",
        18999,
        21999,
        4.1,
        "5g budget battery",
        "Big-battery 5G phone with a 120 Hz display.",
        {
            "Display": '6.6" 120 Hz',
            "Processor": "Dimensity 6100+",
            "RAM": "8 GB",
            "Storage": "128 GB",
            "Battery": "6000 mAh",
            "Camera": "50 MP",
        },
        [(None, "blue", 25, 5), (None, "black", 18, 0)],
    ),
    (
        "Voltix Edge 5G",
        "Voltix",
        "smartphones",
        31999,
        34999,
        4.6,
        "5g camera amoled",
        "Flagship-grade camera and AMOLED display at a mid-range price.",
        {
            "Display": '6.7" AMOLED 120 Hz',
            "Processor": "Snapdragon 7 Gen 3",
            "RAM": "12 GB",
            "Storage": "256 GB",
            "Battery": "5000 mAh",
            "Camera": "50 MP OIS",
        },
        [(None, "black", 9, 0), (None, "green", 2, 0)],
    ),
    (
        "Nimbus Lite 4G",
        "Nimbus",
        "smartphones",
        9999,
        11999,
        3.8,
        "budget basic",
        "Reliable everyday phone with a long-lasting battery.",
        {"Display": '6.5" HD+', "RAM": "4 GB", "Storage": "64 GB", "Battery": "5000 mAh"},
        [(None, "black", 30, 10)],
    ),
    (
        "Voltix Edge Pro",
        "Voltix",
        "smartphones",
        54999,
        59999,
        4.8,
        "5g camera premium",
        "Pro camera system with 3x telephoto and 100 W charging.",
        {
            "Display": '6.8" LTPO AMOLED',
            "Processor": "Snapdragon 8 Gen 3",
            "RAM": "16 GB",
            "Storage": "512 GB",
            "Camera": "50 MP + 3x tele",
        },
        [(None, "silver", 5, 0)],
    ),
    (
        "Auralis Buds ANC",
        "Auralis",
        "audio",
        3999,
        5999,
        4.4,
        "wireless noise cancelling earbuds",
        "True-wireless earbuds with hybrid active noise cancelling.",
        {"Battery": "30 h with case", "ANC": "Hybrid, 35 dB", "Bluetooth": "5.3", "Water resistance": "IPX4"},
        [(None, "black", 40, 10), (None, "white", 22, 0)],
    ),
    (
        "Auralis Studio Over-Ear",
        "Auralis",
        "audio",
        7999,
        11999,
        4.6,
        "wireless noise cancelling headphones",
        "Over-ear headphones with 50-hour battery and LDAC.",
        {"Battery": "50 h", "Driver": "40 mm", "Codecs": "LDAC, AAC", "Weight": "250 g"},
        [(None, "black", 12, 0), (None, "beige", 4, 0)],
    ),
    (
        "Auralis Boom Mini",
        "Auralis",
        "audio",
        2499,
        3499,
        4.2,
        "wireless speaker portable",
        "Pocket Bluetooth speaker with punchy bass and IP67 rating.",
        {"Output": "10 W", "Battery": "14 h", "Water resistance": "IP67"},
        [(None, "red", 15, 0), (None, "blue", 15, 0)],
    ),
    (
        "Stridex Velocity Run",
        "Stridex",
        "footwear",
        2799,
        3999,
        4.5,
        "running road lightweight",
        "Lightweight road-running shoe with responsive foam cushioning.",
        {"Use": "Road running", "Drop": "8 mm", "Weight": "240 g (UK 9)", "Upper": "Engineered mesh"},
        [("7", "black", 6, 2), ("8", "black", 8, 2), ("9", "black", 10, 4), ("10", "black", 3, 0), ("9", "white", 5, 0)],
    ),
    (
        "Stridex Trail Pro",
        "Stridex",
        "footwear",
        4499,
        5499,
        4.3,
        "running trail grip",
        "Trail-running shoe with aggressive lugs and a rock plate.",
        {"Use": "Trail running", "Drop": "6 mm", "Outsole": "Vibram-style rubber"},
        [("8", "black", 4, 0), ("9", "black", 2, 0), ("10", "grey", 5, 0)],
    ),
    (
        "Stridex Daily Walk",
        "Stridex",
        "footwear",
        1999,
        2499,
        4.0,
        "casual walking comfort",
        "Everyday walking shoe with memory-foam insole.",
        {"Use": "Walking", "Upper": "Knit"},
        [("8", "white", 12, 4), ("9", "white", 9, 4), ("9", "navy", 7, 0)],
    ),
    (
        "Stridex Tempo Racer",
        "Stridex",
        "footwear",
        6999,
        8999,
        4.7,
        "running racing carbon",
        "Carbon-plated racing shoe for 5K to marathon.",
        {"Use": "Racing", "Plate": "Carbon", "Drop": "8 mm"},
        [("8", "orange", 3, 0), ("9", "orange", 1, 0)],
    ),
    (
        "Stridex DryFit Tee",
        "Stridex",
        "apparel",
        799,
        1299,
        4.1,
        "running cotton breathable tshirt",
        "Quick-dry training T-shirt.",
        {"Fabric": "Polyester blend", "Fit": "Regular"},
        [("M", "black", 30, 10), ("L", "black", 25, 10), ("M", "white", 20, 0)],
    ),
    (
        "Stridex Thermal Hoodie",
        "Stridex",
        "apparel",
        1899,
        2799,
        4.3,
        "hoodie winter casual",
        "Brushed-fleece hoodie for cool mornings.",
        {"Fabric": "Cotton fleece", "Fit": "Relaxed"},
        [("M", "grey", 10, 0), ("L", "grey", 4, 0), ("XL", "navy", 6, 0)],
    ),
    (
        "Voltix Fit Watch 2",
        "Voltix",
        "wearables",
        4999,
        6999,
        4.2,
        "smartwatch fitness gps",
        "AMOLED smartwatch with GPS and 10-day battery.",
        {"Display": '1.43" AMOLED', "Battery": "10 days", "GPS": "Built-in", "Water resistance": "5 ATM"},
        [(None, "black", 18, 0), (None, "pink", 3, 0)],
    ),
    (
        "Nimbus Band 8",
        "Nimbus",
        "wearables",
        2299,
        2999,
        4.0,
        "fitness band budget",
        "Slim fitness band with SpO2 and sleep tracking.",
        {"Battery": "14 days", "Sensors": "HR, SpO2"},
        [(None, "black", 25, 5)],
    ),
    (
        "HearthCo Electric Kettle 1.5L",
        "HearthCo",
        "home-kitchen",
        1299,
        1799,
        4.3,
        "kettle kitchen",
        "Stainless-steel kettle with auto shut-off.",
        {"Capacity": "1.5 L", "Power": "1500 W"},
        [(None, "silver", 20, 0)],
    ),
    (
        "HearthCo Air Fryer 4L",
        "HearthCo",
        "home-kitchen",
        4999,
        7499,
        4.5,
        "air fryer kitchen healthy",
        "4-litre digital air fryer with 8 presets.",
        {"Capacity": "4 L", "Power": "1400 W", "Presets": "8"},
        [(None, "black", 7, 0)],
    ),
    (
        "HearthCo Mixer Grinder 750W",
        "HearthCo",
        "home-kitchen",
        3299,
        4499,
        4.1,
        "mixer grinder kitchen",
        "750 W mixer grinder with three stainless jars.",
        {"Power": "750 W", "Jars": "3"},
        [(None, "white", 2, 0)],
    ),
]

COUPONS = [("WELCOME10", "PERCENT", "10", "1500", "1000"), ("FLAT500", "FLAT", "500", "4999", None)]


async def seed(session: AsyncSession, *, index_rag: bool = True) -> bool:
    if await session.scalar(select(User.id).limit(1)):
        return False
    rnd = random.Random(42)  # noqa: S311 - deterministic demo data, not security
    now = datetime.now(UTC)

    perms = {code: Permission(code=code) for codes in ROLE_PERMISSIONS.values() for code in codes}
    session.add_all(perms.values())
    roles = {r: RoleModel(name=r.value, permissions=[perms[c] for c in ROLE_PERMISSIONS[r]]) for r in Role}
    session.add_all(roles.values())

    users: dict[str, User] = {}
    for email, pwd, name, phone, rl, addr, budget in DEMO_USERS:
        u = User(email=email, password_hash=hash_password(pwd), full_name=name, phone=phone, roles=[roles[r] for r in rl], addresses=[])
        u.created_at = now - timedelta(days=rnd.randint(120, 400))
        if Role.CUSTOMER in rl:
            u.profile = CustomerProfile(preferred_categories=list(budget), budget_hints=budget, whatsapp_opt_in=email.startswith("asha"))
            label, line1, city, state, pin = addr  # type: ignore[misc]
            u.addresses = [Address(label=label, line1=line1, city=city, state=state, pincode=pin, phone=phone, is_default=True)]
        session.add(u)
        users[email] = u
    await session.flush()
    for u in users.values():
        session.add(ShoppingCart(user_id=u.id))

    whs = [
        Warehouse(code="BLR-1", name="Bengaluru Fulfilment Centre", city="Bengaluru", pincode="560100", priority=1),
        Warehouse(code="MYS-1", name="Mysuru Warehouse", city="Mysuru", pincode="570016", priority=2),
    ]
    brands = {b: Brand(name=b, slug=b.lower()) for b in BRANDS}
    cats = {slug: ProductCategory(name=name, slug=slug) for name, slug in CATEGORIES}
    session.add_all([*whs, *brands.values(), *cats.values()])
    await session.flush()

    products: list[Product] = []
    first_variant: dict[int, ProductVariant] = {}
    for name, brand, cat, price, mrp, rating, tags, desc, specs, variants in PRODUCTS:
        p = Product(
            name=name,
            slug=name.lower().replace(" ", "-").replace(".", ""),
            description=desc,
            brand_id=brands[brand].id,
            category_id=cats[cat].id,
            price=Decimal(price),
            mrp=Decimal(mrp),
            rating=rating,
            rating_count=rnd.randint(40, 900),
            tags=tags,
            specifications=specs,
            images=[ProductImage(url=f"/images/products/{cat}.svg", alt=name)],
        )
        session.add(p)
        await session.flush()
        for i, (size, colour, q_blr, q_mys) in enumerate(variants):
            sku = f"{brand[:3].upper()}-{p.id:03d}-{(colour or 'std')[:3].upper()}{size or ''}-{i}"
            v = ProductVariant(product_id=p.id, sku=sku, size=size, colour=colour)
            session.add(v)
            await session.flush()
            first_variant.setdefault(p.id, v)
            session.add(Inventory(variant_id=v.id, warehouse_id=whs[0].id, quantity=q_blr, reserved=0))
            if q_mys:
                session.add(Inventory(variant_id=v.id, warehouse_id=whs[1].id, quantity=q_mys, reserved=0))
        products.append(p)
    for code, typ, val, min_v, max_d in COUPONS:
        session.add(
            Coupon(
                code=code,
                discount_type=typ,
                value=Decimal(val),
                min_order_value=Decimal(min_v),
                max_discount=Decimal(max_d) if max_d else None,
            )
        )
    await session.flush()

    customers = [users[e] for e in ("asha@nextbot.demo", "rahul@nextbot.demo", "meera@nextbot.demo")]
    for p in products[:12]:
        for c in rnd.sample(customers, 2):
            session.add(Review(product_id=p.id, user_id=c.id, rating=rnd.randint(3, 5), title="Good value", body="Works as described."))

    # ---- sample orders: realistic history for analytics, tracking and the return demo
    async def make_order(user: User, items: list[tuple[Product, int]], status: OrderStatus, days_ago: float) -> Order:
        created = now - timedelta(days=days_ago)
        lines = []
        for p, qty in items:
            v = first_variant[p.id]
            lines.append(
                OrderItem(
                    product_id=p.id,
                    variant_id=v.id,
                    warehouse_id=whs[0].id,
                    product_name=p.name,
                    sku=v.sku,
                    category_slug=cats_by_id[p.category_id],
                    quantity=qty,
                    unit_price=p.price,
                    line_total=p.price * qty,
                )
            )
        t = calculate_totals([LineInput(li.unit_price, li.quantity) for li in lines])
        addr = user.addresses[0]
        suffix = hashlib.sha1(f"{user.id}{days_ago}".encode(), usedforsecurity=False).hexdigest()[:6].upper()
        order = Order(
            order_number=f"NB-{created:%y%m%d}-{suffix}",
            user_id=user.id,
            status=status,
            subtotal=t.subtotal,
            discount=t.discount,
            tax=t.tax,
            shipping_fee=t.shipping,
            total=t.total,
            shipping_pincode=addr.pincode,
            items=lines,
            shipping_address={"line1": addr.line1, "city": addr.city, "state": addr.state, "pincode": addr.pincode, "phone": addr.phone},
            confirmed_at=created + timedelta(minutes=2),
        )
        order.created_at = created
        if status == OrderStatus.DELIVERED:
            order.delivered_at = created + timedelta(days=2)
        session.add(order)
        await session.flush()
        session.add(
            Payment(
                order_id=order.id,
                user_id=user.id,
                provider="mock",
                method="mock_upi",
                amount=order.total,
                status=PaymentStatus.SUCCEEDED,
                idempotency_key=f"seed-{order.id}",
                provider_reference=f"mock_pay_seed_{order.id}",
                is_simulated=True,
            )
        )
        ship_status = {
            OrderStatus.DELIVERED: ShipmentStatus.DELIVERED,
            OrderStatus.SHIPPED: ShipmentStatus.SHIPPED,
            OrderStatus.PROCESSING: ShipmentStatus.CREATED,
        }.get(status)
        if ship_status:
            steps = [
                ShipmentStatus.CREATED,
                ShipmentStatus.PACKED,
                ShipmentStatus.SHIPPED,
                ShipmentStatus.OUT_FOR_DELIVERY,
                ShipmentStatus.DELIVERED,
            ]
            events = [
                {
                    "status": s.value,
                    "at": (created + timedelta(hours=6 * i)).isoformat(),
                    "note": s.value.replace("_", " ").title(),
                    "location": "Bengaluru FC" if i < 2 else addr.city,
                }
                for i, s in enumerate(steps[: steps.index(ship_status) + 1])
            ]
            session.add(
                Shipment(
                    order_id=order.id,
                    carrier="MockExpress",
                    tracking_number=f"MX{order.id:06d}SEED",
                    status=ship_status,
                    estimated_delivery=(created + timedelta(days=3)).date(),
                    events=events,
                    is_simulated=True,
                )
            )
        return order

    cats_by_id = {c.id: slug for slug, c in cats.items()}
    by_name = {p.name: p for p in products}
    asha, rahul, meera = customers
    await make_order(asha, [(by_name["Stridex Velocity Run"], 1)], OrderStatus.DELIVERED, 4)  # return demo (inside window)
    await make_order(asha, [(by_name["Auralis Buds ANC"], 1)], OrderStatus.DELIVERED, 40)
    await make_order(rahul, [(by_name["Auralis Studio Over-Ear"], 1)], OrderStatus.DELIVERED, 25)  # outside return window
    await make_order(rahul, [(by_name["Nimbus Note 5G"], 1), (by_name["Auralis Boom Mini"], 1)], OrderStatus.SHIPPED, 1.5)
    await make_order(meera, [(by_name["Voltix AirBook 14"], 1)], OrderStatus.PROCESSING, 0.5)
    for i in range(14):  # spread of paid orders over the last 60 days for the analytics dashboards
        c = customers[i % 3]
        picks = rnd.sample(products, rnd.randint(1, 2))
        await make_order(c, [(p, 1) for p in picks], OrderStatus.DELIVERED, rnd.uniform(5, 60))

    # ---- knowledge base documents (chunks/embeddings are built by the RAG indexer at startup)
    for d in load_markdown_docs():
        session.add(
            KnowledgeDocument(
                id=d.doc_id,
                title=d.title,
                category=d.category,
                source=d.source,
                content=d.content,
                checksum=hashlib.sha256(d.content.encode()).hexdigest(),
            )
        )
    await session.flush()
    return True


async def _main() -> None:
    from app.core.config import get_settings
    from app.database.base import Base
    from app.database.session import get_engine, init_engine, session_factory

    s = get_settings()
    init_engine(s.database_url)
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory()() as session:
        created = await seed(session)
        await session.commit()
    print("seeded" if created else "already seeded")


if __name__ == "__main__":
    asyncio.run(_main())
