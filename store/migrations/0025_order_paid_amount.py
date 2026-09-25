from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0024_rename_discount_coupon_discount_percent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='paid_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]