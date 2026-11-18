from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_seed_staff_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='razorpay_refund_id',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='order',
            name='refunded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
