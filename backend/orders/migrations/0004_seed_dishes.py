"""
Data migration: seeds all E-Homely dishes from the known menu.
Skips any dish that already exists (by name) so it is safe to run twice.
Images reference files already present in media/dishes/.
Daily limits: Biriyani-Full, Biriyani-Single, and Meals are capped at 75.
"""
from django.db import migrations


DISHES = [
    # (name, meal, category, price, daily_limit, image_filename)
    # ── Breakfast ──────────────────────────────────────────────
    ('Appam',       'breakfast', 'Main',  12,  0, 'APPAM.jpeg'),
    ('Puttu',       'breakfast', 'Main',  15,  0, 'PUTTU.jpeg'),
    ('Chapathi',    'breakfast', 'Main',  12,  0, 'CHAPATHI.jpeg'),
    ('Boiled Egg',  'breakfast', 'Side',  10,  0, 'BOILED_EGG.jpeg'),
    ('Kadala Curry','breakfast', 'Side',  30,  0, 'KADALA_CURRY.jpeg'),
    ('Egg Curry',   'breakfast', 'Side',  30,  0, 'EGG_CURRY.jpeg'),
    # ── Lunch ──────────────────────────────────────────────────
    ('Meals',           'lunch', 'Main',  60, 75, 'MEALS.jpeg'),
    ('Biriyani-Full',   'lunch', 'Main',  150, 75, 'BIRIYANI-FULL.jpeg'),
    ('Biriyani-Single', 'lunch', 'Main',  80, 75, 'BIRIYANI-SINGLE.jpeg'),
    ('Chicken Fry',     'lunch', 'Side',  100,  0, 'CHICKEN_FRY.jpeg'),
    # ── Dinner ─────────────────────────────────────────────────
    ('Appam',        'dinner', 'Main',  12,  0, 'APPAM.jpeg'),
    ('Puttu',        'dinner', 'Main',  15,  0, 'PUTTU.jpeg'),
    ('Chapathi',     'dinner', 'Main',  12,  0, 'CHAPATHI.jpeg'),
    ('Idiyappam',    'dinner', 'Main',  12,  0, 'IDIYAPPAM.jpeg'),
    ('Boiled Egg',   'dinner', 'Side',  10,  0, 'BOILED_EGG.jpeg'),
    ('Kadala Curry', 'dinner', 'Side',  30,  0, 'KADALA_CURRY.jpeg'),
    ('Egg Curry',    'dinner', 'Side',  30,  0, 'EGG_CURRY.jpeg'),
    ('Chicken Curry','dinner', 'Side',  60,  0, 'CHICKEN_CURRY.jpeg'),
    ('Beef Gravy',   'dinner', 'Side',  100,  0, 'BEEF_GRAVY.jpeg'),
    ('Chicken Fry',  'dinner', 'Side',  100,  0, 'CHICKEN_FRY.jpeg'),
]


def seed_dishes(apps, schema_editor):
    Dish = apps.get_model('orders', 'Dish')
    for name, meal, category, price, daily_limit, image_file in DISHES:
        if Dish.objects.filter(name=name, meal=meal).exists():
            continue  # already seeded — skip
        Dish.objects.create(
            name=name,
            meal=meal,
            category=category,
            price=price,
            daily_limit=daily_limit,
            is_available=True,
            image=f'dishes/{image_file}',
        )


def unseed_dishes(apps, schema_editor):
    # Reverse: remove only dishes that match our seeded names exactly.
    Dish = apps.get_model('orders', 'Dish')
    for name, meal, *_ in DISHES:
        Dish.objects.filter(name=name, meal=meal).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_preorder_and_limits'),
    ]

    operations = [
        migrations.RunPython(seed_dishes, reverse_code=unseed_dishes),
    ]
