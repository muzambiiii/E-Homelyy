from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_order_order_no_unique'),
    ]

    operations = [
        # Add daily_limit to Dish (0 = no limit)
        migrations.AddField(
            model_name='dish',
            name='daily_limit',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='0 = no limit. Set to e.g. 75 to cap daily orders for this dish.',
            ),
        ),
        # Add meal to Order so we know which meal window the order belongs to
        migrations.AddField(
            model_name='order',
            name='meal',
            field=models.CharField(
                choices=[('breakfast', 'Breakfast'), ('lunch', 'Lunch'), ('dinner', 'Dinner')],
                default='lunch',
                max_length=10,
            ),
        ),
    ]
