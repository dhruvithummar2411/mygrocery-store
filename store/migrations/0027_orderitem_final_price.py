from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0026_khata_customer_khata_entry'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='final_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
