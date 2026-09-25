from django.contrib import admin
from .models import Product,Category,Subcategory,Coupon,ProductVariant,ProductRating
from .models import OfferTip, Order, OrderItem

admin.site.register(Category)
admin.site.register(Subcategory)
admin.site.register(ProductRating)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 3
    fields = ['weight','price', 'cut_price','discount']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display=['name','stock','category','is_flash_deal','flash_end_time']
    list_editable=['is_flash_deal']
    list_filter=['is_flash_deal','category']
    fields = [
        'name', 'price', 'discount_percent', 'stock', 'category', 'subcategory',
        'description', 'delivery_time', 'image', 'is_flash_deal', 'flash_end_time'
    ]
    inlines= [ProductVariantInline]
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'min_order_amount', 'max_usage', 'used_count', 'expiry_date', 'is_active')


admin.site.register(OfferTip)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ['product_name', 'qty', 'price', 'final_price']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_name', 'customer_phone', 'total_amount', 'paid_amount', 'status', 'created_at']
    list_editable = ['status']
    list_filter = ['status', 'created_at']
    search_fields = ['id', 'customer_name', 'customer_phone']
    inlines = [OrderItemInline]

