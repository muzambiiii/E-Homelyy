from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0006_order_refund_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='for_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
