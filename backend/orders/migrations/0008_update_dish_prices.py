"""Data migration: sets every dish to the current menu prices (matched by name + meal).
Safe to run on an existing database; dishes that are not listed are left untouched."""
from django.db import migrations

PRICES = [
    # (name, meal, price)
    ('Appam', 'breakfast', 12),
    ('Puttu', 'breakfast', 15),
    ('Chapathi', 'breakfast', 12),
    ('Boiled Egg', 'breakfast', 10),
    ('Kadala Curry', 'breakfast', 30),
    ('Egg Curry', 'breakfast', 30),
    ('Meals', 'lunch', 60),
    ('Biriyani-Full', 'lunch', 150),
    ('Biriyani-Single', 'lunch', 80),
    ('Chicken Fry', 'lunch', 100),
    ('Appam', 'dinner', 12),
    ('Puttu', 'dinner', 15),
    ('Chapathi', 'dinner', 12),
    ('Idiyappam', 'dinner', 12),
    ('Boiled Egg', 'dinner', 10),
    ('Kadala Curry', 'dinner', 30),
    ('Egg Curry', 'dinner', 30),
    ('Chicken Curry', 'dinner', 60),
    ('Beef Gravy', 'dinner', 100),
    ('Chicken Fry', 'dinner', 100),
]


def set_prices(apps, schema_editor):
    Dish = apps.get_model('orders', 'Dish')
    for name, meal, price in PRICES:
        Dish.objects.filter(name__iexact=name, meal=meal).update(price=price)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0007_order_for_date'),
    ]

    operations = [
        migrations.RunPython(set_prices, migrations.RunPython.noop),
    ]
