from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Category(models.Model):
    name=models.CharField(max_length=100,unique=True)

    def __str__(self):
        return self.name

class Subcategory(models.Model):
    category = models.ForeignKey(Category,on_delete=models.CASCADE,related_name='subcategories')
    name=models.CharField(max_length=100)

    def __str__(self):
        return f"{self.category.name}-{self.name}"
    

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('Percentage', 'Percentage'),
        ('Flat', 'Flat'),
    ]
    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='Percentage')
    discount_value = models.IntegerField(default=10) # e.g., 10 for 10% or 100 for Rs 100
    min_order_amount = models.IntegerField(default=0)
    max_usage = models.IntegerField(default=1)
    used_count = models.IntegerField(default=0)
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def discount_percent(self):
        return self.discount_value

    @property
    def min_amount(self):
        return self.min_order_amount

    @property
    def active(self):
        return self.is_active

    @active.setter
    def active(self, val):
        self.is_active = val

    @property
    def expired_date(self):
        return self.expiry_date

    def __str__(self):
        return f"{self.code} ({self.discount_type}: {self.discount_value})"


from django.db.models import Avg

# Create your models here.
class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/',blank=True,null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE,related_name='products')
    subcategory = models.ForeignKey(Subcategory,on_delete=models.SET_NULL,null=True,blank=True)
    description = models.TextField(blank=True, null=True)
    delivery_time=models.CharField(max_length=20,default="10 MINS")
    discount_percent=models.IntegerField(default=0,help_text="0 daaloge to OFF nahi dikhega,20 daaloge to 20% OFF")
    is_flash_deal = models.BooleanField(default=False)
    flash_end_time = models.DateTimeField(null=True, blank=True)
    
    def __str__( self ):
        return self.name

    @property
    def discounted_price(self):
        if self.discount_percent and self.discount_percent > 0:
            return int(self.price * (100 - self.discount_percent) / 100)
        return self.price

    @property
    def average_rating(self):
        avg = self.ratings.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg is not None else 0.0

    @property
    def rating_count(self):
        return self.ratings.count()

    @property
    def stars_breakdown(self):
        score = self.average_rating
        full = int(score)
        decimal_part = score - full
        half = 1 if decimal_part >= 0.25 and decimal_part < 0.75 else 0
        if decimal_part >= 0.75:
            full += 1
            half = 0
        empty = max(0, 5 - full - half)
        return {
            'full': range(full),
            'half': half > 0,
            'empty': range(empty),
            'score': score,
        }
    
class ProductVariant(models.Model):
    product = models.ForeignKey(Product,on_delete=models.CASCADE,related_name='variants')
    weight = models.CharField(max_length=50)
    price = models. DecimalField(max_digits=10, decimal_places=2)
    cut_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount = models.IntegerField(default=0)
    stock = models.IntegerField(default=0)

    def __str__(self):
       return f"{self.product.name}- {self.weight}"

    @property
    def name(self):
        return self.weight


class LoginLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address=models.GenericIPAddressField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.login_time}"


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    customer_name = models.CharField(max_length=100, default="Guest")
    customer_phone = models.CharField(max_length=30, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_received = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_code = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='Ordered', choices=[
        ('Ordered','Ordered'),
        ('Packed','Packed'),
        ('Shipped','Shipped'),
        ('Delivered','Delivered'),
        ('Cancelled','Cancelled')
    ])

    payment_method = models.CharField(max_length=50, default='Cash on Delivery')
    payment_status = models.CharField(max_length=20, default='PENDING')
    cash_collected = models.BooleanField(default=False)
    cash_amount_received = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cash_collected_at = models.DateTimeField(null=True, blank=True)
    cash_collected_by = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Order #{self.id} - {self.total_amount}"

    @property
    def total(self):
        return self.total_amount

    @property
    def is_paid(self):
        """True if cash has been recorded and covers the full amount."""
        if self.cash_collected or self.payment_status == 'PAID':
            return True
        return self.cash_received is not None and self.cash_received >= self.total_amount

    @property
    def due_amount(self):
        if self.is_paid:
            return Decimal('0')
        return self.total_amount

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField(max_length=200)
    qty = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    @property
    def bill_price(self):
        return self.final_price if self.final_price is not None else self.price

    @property
    def quantity(self):
        return self.qty

    @property
    def total(self):
        return Decimal(self.qty) * self.bill_price

class OfferTip(models.Model):
    text = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.text

class ProductRating(models.Model):
    RATING_CHOICES = [
        (0.5, '0.5 ★'),
        (1.0, '1.0 ★'),
        (1.5, '1.5 ★'),
        (2.0, '2.0 ★'),
        (2.5, '2.5 ★'),
        (3.0, '3.0 ★'),
        (3.5, '3.5 ★'),
        (4.0, '4.0 ★'),
        (4.5, '4.5 ★'),
        (5.0, '5.0 ★'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_ratings')
    rating = models.FloatField(choices=RATING_CHOICES)
    review = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} rated {self.product.name} - {self.rating}★"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('user', 'product'),)

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"


