"""Catalog factory — builds a realistic product catalog the gym uses
across all tasks.

The catalog is intentionally larger than any single task needs (around
30 SKUs across 6 categories) so search/filter results are non-trivial
and the agent has to actually navigate rather than picking the only
matching product.
"""

from __future__ import annotations

from server.state import Product, ProductVariant, Review


def _laptop_variants() -> list[ProductVariant]:
    return [
        ProductVariant("v_lt_16_512",  "16GB RAM / 512GB SSD",
                       {"ram": "16GB", "storage": "512GB"}, 0.0, 6),
        ProductVariant("v_lt_16_1tb",  "16GB RAM / 1TB SSD",
                       {"ram": "16GB", "storage": "1TB"}, 150.0, 4),
        ProductVariant("v_lt_32_1tb",  "32GB RAM / 1TB SSD",
                       {"ram": "32GB", "storage": "1TB"}, 400.0, 2),
    ]


def _build_catalog() -> dict[str, Product]:
    return {
        # ----- Electronics: laptops, mice, keyboards, monitors -----
        "p_laptop_studio": Product(
            id="p_laptop_studio", name="Studio Laptop 14",
            brand="LumeBook", category="electronics", base_price=899.99,
            rating=4.6, review_count=128, stock=12,
            image_emoji="💻",
            short_description="Mid-range 14-inch creator's laptop.",
            long_description=(
                "Lightweight 14-inch laptop with anti-glare display. "
                "Great for creators on a budget. Configurable RAM/SSD."
            ),
            tags=["laptop", "creator", "14-inch"],
            # Variants are added per-task; default is the base config so
            # add_to_cart works without explicit variant selection.
            variants=[],
            reviews=[
                Review("r1", "Aisha", 5, "Great value",
                       "Perfect for my workflow.", verified_purchase=True),
                Review("r2", "Marco", 4, "Display is sharp",
                       "Just wish the battery lasted longer."),
            ],
            weight_kg=1.4,
        ),
        "p_laptop_pro": Product(
            id="p_laptop_pro", name="Pro Laptop X1",
            brand="LumeBook", category="electronics", base_price=1499.99,
            rating=4.8, review_count=412, stock=5,
            image_emoji="💻",
            short_description="High-end pro laptop.",
            long_description="Premium 16-inch laptop for power users.",
            tags=["laptop", "pro", "16-inch"],
        ),
        "p_laptop_budget": Product(
            id="p_laptop_budget", name="Budget Laptop Lite",
            brand="GenericTech", category="electronics", base_price=549.99,
            rating=3.6, review_count=92, stock=20,
            image_emoji="💻",
            short_description="Entry-level laptop.",
            long_description="Cheap but slow. 8GB RAM, 256GB.",
            tags=["laptop", "budget"],
        ),
        "p_mouse_wireless": Product(
            id="p_mouse_wireless", name="Wireless Mouse",
            brand="Logitech", category="electronics", base_price=29.99,
            rating=4.4, review_count=2811, stock=58,
            image_emoji="🖱️",
            short_description="Standard wireless mouse.",
            long_description="Reliable 2.4GHz wireless mouse with USB receiver.",
            tags=["mouse", "wireless"],
        ),
        "p_mouse_gaming": Product(
            id="p_mouse_gaming", name="Wireless Gaming Mouse",
            brand="Razer", category="electronics", base_price=79.99,
            rating=4.6, review_count=1240, stock=22,
            image_emoji="🖱️",
            short_description="High-DPI gaming mouse with RGB.",
            long_description="Pro-grade gaming mouse with customizable RGB.",
            tags=["mouse", "gaming"],
        ),
        "p_kb_mech": Product(
            id="p_kb_mech", name="Mechanical Keyboard",
            brand="Keychron", category="electronics", base_price=119.99,
            rating=4.5, review_count=856, stock=18,
            image_emoji="⌨️",
            short_description="Hot-swappable mechanical keyboard.",
            long_description="Compact 75% layout, hot-swap PCB, Cherry switches.",
            tags=["keyboard", "mechanical"],
        ),
        "p_kb_wireless": Product(
            id="p_kb_wireless", name="Wireless Keyboard",
            brand="Logitech", category="electronics", base_price=59.99,
            rating=4.3, review_count=1932, stock=33,
            image_emoji="⌨️",
            short_description="Slim wireless keyboard.",
            tags=["keyboard", "wireless"],
        ),
        "p_monitor_24": Product(
            id="p_monitor_24", name="24-inch Monitor",
            brand="Dell", category="electronics", base_price=199.99,
            rating=4.4, review_count=540, stock=15,
            image_emoji="🖥️",
            short_description="1080p 24-inch IPS monitor.",
            tags=["monitor", "24-inch"],
        ),
        "p_monitor_27": Product(
            id="p_monitor_27", name="27-inch Monitor",
            brand="LG", category="electronics", base_price=329.99,
            rating=4.7, review_count=312, stock=8,
            image_emoji="🖥️",
            short_description="1440p 27-inch monitor.",
            tags=["monitor", "27-inch", "1440p"],
        ),

        # ----- Audio -----
        "p_hp_premium": Product(
            id="p_hp_premium", name="Bluetooth Headphone Premium",
            brand="Sony", category="audio", base_price=249.99,
            rating=4.8, review_count=2100, stock=8,
            image_emoji="🎧",
            short_description="ANC over-ear, 30h battery.",
            long_description="Industry-leading active noise cancellation.",
            tags=["headphones", "bluetooth", "anc"],
        ),
        "p_hp_studio": Product(
            id="p_hp_studio", name="Bluetooth Headphone Studio",
            brand="Audio-Technica", category="audio", base_price=129.99,
            rating=4.5, review_count=812, stock=12,
            image_emoji="🎧",
            short_description="Studio-grade comfort.",
            tags=["headphones", "studio"],
        ),
        "p_hp_lite": Product(
            id="p_hp_lite", name="Bluetooth Headphone Lite",
            brand="JBL", category="audio", base_price=49.99,
            rating=4.1, review_count=4280, stock=42,
            image_emoji="🎧",
            short_description="Lightweight everyday headphones.",
            tags=["headphones", "budget"],
        ),
        "p_speaker": Product(
            id="p_speaker", name="Bluetooth Speaker",
            brand="JBL", category="audio", base_price=79.99,
            rating=4.4, review_count=1280, stock=20,
            image_emoji="🔊",
            short_description="Portable wireless speaker.",
            tags=["speaker", "bluetooth"],
        ),

        # ----- Books -----
        "p_book_cook": Product(
            id="p_book_cook", name="The Joy of Cooking",
            brand="Scribner", category="books", base_price=24.99,
            rating=4.6, review_count=920, stock=8,
            image_emoji="📕",
            short_description="Classic American cookbook.",
            tags=["cookbook"],
        ),
        "p_book_sci_fi": Product(
            id="p_book_sci_fi", name="Project Hail Mary",
            brand="Ballantine", category="books", base_price=16.50,
            rating=4.8, review_count=15300, stock=14,
            image_emoji="📚",
            short_description="Andy Weir sci-fi novel.",
            tags=["fiction", "sci-fi"],
        ),
        "p_book_history": Product(
            id="p_book_history", name="Sapiens",
            brand="Harper", category="books", base_price=19.99,
            rating=4.7, review_count=23800, stock=20,
            image_emoji="📘",
            short_description="A brief history of humankind.",
            tags=["nonfiction", "history"],
        ),
        "p_book_oos": Product(
            id="p_book_oos", name="The Power Broker",
            brand="Knopf", category="books", base_price=32.00,
            rating=4.9, review_count=6200, stock=0,            # OOS!
            image_emoji="📗",
            short_description="Robert Caro classic. OUT OF STOCK.",
            tags=["nonfiction", "biography"],
        ),

        # ----- Clothing -----
        "p_clothing_tshirt": Product(
            id="p_clothing_tshirt", name="Cotton T-Shirt",
            brand="Everlane", category="clothing", base_price=24.99,
            rating=4.2, review_count=820, stock=120,
            image_emoji="👕",
            short_description="Classic cotton t-shirt.",
            variants=[
                ProductVariant("v_ts_s_blk", "S — Black",
                               {"size": "S", "color": "black"}, 0.0, 30),
                ProductVariant("v_ts_m_blk", "M — Black",
                               {"size": "M", "color": "black"}, 0.0, 25),
                ProductVariant("v_ts_l_blk", "L — Black",
                               {"size": "L", "color": "black"}, 0.0, 15),
                ProductVariant("v_ts_m_wht", "M — White",
                               {"size": "M", "color": "white"}, 0.0, 25),
                ProductVariant("v_ts_l_wht", "L — White",
                               {"size": "L", "color": "white"}, 0.0, 25),
            ],
            tags=["tshirt"],
        ),
        "p_clothing_hoodie": Product(
            id="p_clothing_hoodie", name="Pullover Hoodie",
            brand="Champion", category="clothing", base_price=49.99,
            rating=4.5, review_count=3120, stock=80,
            image_emoji="🧥",
            short_description="Heavyweight pullover hoodie.",
            tags=["hoodie"],
        ),

        # ----- Home -----
        "p_home_lamp": Product(
            id="p_home_lamp", name="Modern Desk Lamp",
            brand="IKEA", category="home", base_price=39.99,
            rating=4.1, review_count=210, stock=25,
            image_emoji="💡",
            short_description="Adjustable LED desk lamp.",
            tags=["lamp"],
        ),
        "p_home_mug": Product(
            id="p_home_mug", name="Ceramic Coffee Mug Set (4)",
            brand="Le Creuset", category="home", base_price=44.99,
            rating=4.6, review_count=512, stock=18,
            image_emoji="☕",
            short_description="Set of 4 ceramic mugs.",
            tags=["mug"],
        ),

        # ----- Subscribable: pet food -----
        "p_pet_food": Product(
            id="p_pet_food", name="Premium Dog Food (5 lb)",
            brand="Wellness", category="pet", base_price=34.99,
            rating=4.7, review_count=4820, stock=120,
            image_emoji="🐶",
            short_description="Grain-free premium dog food.",
            long_description=(
                "Premium dog food, 5 lb bag. Available as a one-time "
                "purchase or weekly/biweekly subscription with a "
                "loyalty discount for gold members."
            ),
            tags=["pet", "dog", "subscription"],
            is_subscribable=True,
        ),

        # ----- Office (adversarial: looks like electronics but isn't) -----
        "p_office_display": Product(
            id="p_office_display", name="Office Display Pro",
            brand="Acer", category="office", base_price=159.99,
            rating=4.3, review_count=120, stock=15,
            image_emoji="🖥️",
            short_description="Office-grade display.",
            long_description=(
                "Looks like a monitor but listed under 'office' category. "
                "Adversarial: tasks that require 'electronics' won't match this."
            ),
            tags=["display"],
        ),
    }
