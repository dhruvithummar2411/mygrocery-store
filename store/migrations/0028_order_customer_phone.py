from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0027_orderitem_final_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='customer_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
