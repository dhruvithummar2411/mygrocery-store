from .models import Coupon, Wishlist
from django.contrib.auth.models import User

def active_save10(request):
    cart = request.session.get('cart', {})
    cart_total = 0
    if isinstance(cart, dict):
        for item in cart.values():
            if isinstance(item, dict):
                cart_total += item.get('qty', 0)
            elif isinstance(item, (int, float)):
                cart_total += int(item)
    return {
        'save10_coupon': Coupon.objects.filter(code__iexact='SAVE10', is_active=True).first(),
        'cart_total': cart_total,
    }

def wishlist_count(request):
    count = 0
    wishlist_ids = []

    customer_user = None
    is_customer_logged_in = False

    # Prefer customer_id from session (set at login)
    cust_id = request.session.get('customer_id')
    if cust_id:
        customer_user = User.objects.filter(id=cust_id).first()
        if customer_user:
            is_customer_logged_in = True

    # Fallback: if Django session has authenticated non-admin user
    if not is_customer_logged_in and request.user.is_authenticated and not request.user.is_staff:
        customer_user = request.user
        is_customer_logged_in = True
        # Sync customer_id into session so subsequent requests are faster
        request.session['customer_id'] = request.user.id

    if customer_user:
        wishlist_qs = Wishlist.objects.filter(user=customer_user)
        count = wishlist_qs.count()
        wishlist_ids = list(wishlist_qs.values_list('product_id', flat=True))

    return {
        'wishlist_count': count,
        'wishlist_product_ids': wishlist_ids,
        'is_customer_logged_in': is_customer_logged_in,
        'customer_user': customer_user,
    }
