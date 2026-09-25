from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0025_order_paid_amount'),
    ]

    operations = [
        migrations.CreateModel(
            name='KhataCustomer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='KhataEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bill_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('jama_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('note', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                    ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='store.khatacustomer')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]