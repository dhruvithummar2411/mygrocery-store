from urllib.parse import quote
from decimal import Decimal
from django.shortcuts import render,redirect,get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from .models import Product,Category,Subcategory,Coupon,ProductVariant,LoginLog
from datetime import timedelta
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.db.models import Q,Sum,Count,F,OuterRef,Subquery,Value,IntegerField
from django.db.models.functions import Coalesce
from django.contrib.auth.models import User
from django.contrib.auth import authenticate,login,logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required,user_passes_test
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django import forms
from .models import Order, OrderItem, OfferTip, ProductRating
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from .models import Wishlist
from django.http import JsonResponse




def home(request):
    query = request.GET.get('q','').strip()
    category_id = request.GET.get('category')
    subcategory_id = request.GET.get('subcategory')

    categories = Category.objects.all().prefetch_related('subcategories')
    products = Product.objects.all() 
    subcategories = Subcategory.objects.all()
    offers = OfferTip.objects.filter(is_active=True)

    if query:
        products = products.filter(Q(name__icontains=query) | Q(category__name__icontains=query))

    if category_id:
        if category_id.isdigit():
            products = products.filter(category_id=category_id)
            subcategories = Subcategory.objects.filter(category_id=category_id)
        else:
            products = products.filter(category__name__iexact=category_id.strip())
            subcategories = Subcategory.objects.filter(category__name__iexact=category_id.strip())

    if subcategory_id:
        if str(subcategory_id).isdigit():
            products = products.filter(subcategory_id=subcategory_id)
        else:
            products = products.filter(subcategory__name=subcategory_id)
    sold_quantity = OrderItem.objects.filter(
        product_name=OuterRef('name')
    ).values('product_name').annotate(total=Sum('qty')).values('total')[:1]
    ranked_products = Product.objects.annotate(
        sold_quantity=Coalesce(
            Subquery(sold_quantity, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        )
    ).order_by('-sold_quantity', 'name')
    if category_id:
        if category_id.isdigit():
            ranked_products = ranked_products.filter(category_id=category_id)
        else:
            ranked_products = ranked_products.filter(category__name__iexact=category_id.strip())
    if subcategory_id:
        if str(subcategory_id).isdigit():
            ranked_products = ranked_products.filter(subcategory_id=subcategory_id)
        else:
            ranked_products = ranked_products.filter(subcategory__name__iexact=subcategory_id.strip())
    best_sellers = list(ranked_products[:4])
    has_sales = any(product.sold_quantity > 0 for product in best_sellers)
    if not has_sales:
        best_sellers = list(ranked_products.filter(
            Q(name__icontains='Mother Dairy') | Q(name__icontains='Amul')
        )[:4])
        for product in best_sellers:
            product.is_bestseller = True
    for product in best_sellers:
        if not getattr(product, 'is_bestseller', False):
            product.is_bestseller = product.sold_quantity > 10

    buy_again_products = []
    if request.user.is_authenticated:
        order_items = OrderItem.objects.filter(order__user=request.user).order_by('-order__created_at', '-id')
        ordered_names = []
        seen = set()
        for item in order_items:
            name = item.product_name.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                ordered_names.append(name)
        
        if ordered_names:
            matched_products = {p.name.lower(): p for p in Product.objects.filter(name__in=ordered_names)}
            for name in ordered_names:
                p = matched_products.get(name.lower())
                if p and p not in buy_again_products:
                    buy_again_products.append(p)
    if not buy_again_products:
        buy_again_products = list(Product.objects.all().order_by('id')[:8])

    selected_cat = None
    if category_id:
        if str(category_id).isdigit():
            selected_cat = int(category_id)
        else:
            cat_obj = Category.objects.filter(name__iexact=category_id.strip()).first()
            selected_cat = cat_obj.id if cat_obj else category_id

    selected_subcat = None
    if subcategory_id:
        if str(subcategory_id).isdigit():
            selected_subcat = int(subcategory_id)
        else:
            sub_obj = Subcategory.objects.filter(name__iexact=str(subcategory_id).strip()).first()
            selected_subcat = sub_obj.id if sub_obj else subcategory_id

    context = {
        'products' : products,
        'categories' : categories,
        'subcategories' : subcategories,
        'selected_category': selected_cat,
        'selected_subcategory': selected_subcat,
        'best_sellers': best_sellers,
        'most_bought_products': best_sellers,
        'offers': offers,
        'buy_again_products': buy_again_products,
        'query':query,
    }
    return render(request, 'store/home.html', context)
def index(request):
    return home(request)
def is_admin(user):
    return getattr(user, 'is_authenticated', False) and (user.is_staff or user.is_superuser)

def admin_required(view_func):
    @never_cache
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            request.session['admin_user_id'] = request.user.id
            return view_func(request, *args, **kwargs)
        
        admin_id = request.session.get('admin_user_id')
        if admin_id:
            admin_user = User.objects.filter(id=admin_id).first()
            if admin_user and (admin_user.is_staff or admin_user.is_superuser):
                login(request, admin_user)
                request.session['admin_user_id'] = admin_id
                return view_func(request, *args, **kwargs)
        
        return redirect('admin_login')
    return wrapper

@admin_required
def admin_dashboard(request):
    total_products = Product.objects.count()
    total_stock = Product.objects.aggregate(Sum('stock'))['stock__sum'] or 0
    total_logins = User.objects.count()
    today_logins = LoginLog.objects.filter(login_time__date=timezone.now().date()).count()
    low_stock_products = Product.objects.filter(stock__lt=10).order_by('stock')

    # Order aur Revenue ke liye 
    total_orders = Order.objects.count()
    today_orders = Order.objects.filter(created_at__date=timezone.now().date()).count()
    all_orders_sum= Order.objects.aggregate(Sum('total_amount'))['total_amount__sum']
    total_revenue=all_orders_sum if all_orders_sum else 0
    today_sum = Order.objects.filter(created_at__date=timezone.now().date()).aggregate(Sum('total_amount'))['total_amount__sum'] 
    today_revenue=today_sum if today_sum else 0
    
    # Chart ke liye data
    categories = Category.objects.all()
    cat_names = [c.name for c in categories]
    cat_counts = [Product.objects.filter(category=c).count() for c in categories]
    cat_stock = [Product.objects.filter(category=c).aggregate(Sum('stock'))['stock__sum'] or 0 for c in categories]
    
    products = Product.objects.all().order_by('-id')
    subcategories = Subcategory.objects.select_related('category').order_by('category__name', 'name')

    context = {
        'total_products': total_products,
        'total_stock': total_stock,
        'products': products,
        'cat_names': cat_names,
        'cat_counts': cat_counts,
        'cat_stock': cat_stock,
        'categories':categories,
        'total_logins':total_logins,
        'today_logins':today_logins,
        'low_stock_products':low_stock_products,
        'total_orders':total_orders,
        'today_orders':today_orders,
        'total_revenue':total_revenue,
        'subcategories': subcategories,
    }
    return render(request, 'store/admin_dashboard.html', context)

@admin_required
def admin_orders(request):
    orders = Order.objects.all().order_by('-created_at')
    return render(request, 'store/admin_orders.html', {'orders': orders})

@admin_required
def clear_order_due(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        order.paid_amount = order.total_amount
        order.save(update_fields=['paid_amount'])
        messages.success(request, f'Order #{order.id} ka due clear ho gaya.')
    return redirect('admin_dashboard')




@admin_required
def add_product(request):
    if request.method == 'POST':
        try:
            discount_percent = int(request.POST.get('discount_percent', 0) or 0)
            if not 0 <= discount_percent <= 100:
                raise ValueError
            
            # Flash deal logic
            is_flash_deal = request.POST.get('is_flash_deal') == 'on'
            flash_end_time = None
            if is_flash_deal:
                raw_time = request.POST.get('flash_end_time')
                if raw_time and raw_time.strip():
                    parsed = parse_datetime(raw_time.strip())
                    if parsed:
                        if timezone.is_naive(parsed):
                            parsed = timezone.make_aware(parsed)
                        flash_end_time = parsed
                    else:
                        flash_end_time = timezone.now() + timedelta(minutes=10)
                else:
                    flash_end_time = timezone.now() + timedelta(minutes=10)

            product = Product.objects.create(
                name=request.POST['name'],
                price=request.POST['price'],
                discount_percent=discount_percent,
                stock=request.POST['stock'],
                category_id=request.POST['category'],
                subcategory_id=request.POST.get('subcategory') or None,
                description=request.POST.get('description', ''),
                image=request.FILES.get('image'),
                is_flash_deal=is_flash_deal,
                flash_end_time=flash_end_time
            )
            for weight, price, stock in zip(request.POST.getlist('weight[]'), request.POST.getlist('variant_price[]'), request.POST.getlist('variant_stock[]')):
                if weight and price:
                    ProductVariant.objects.create(product=product, weight=weight, price=price, stock=int(stock or 0))
            messages.success(request, 'Product added!')
            return redirect('admin_dashboard')
        except (ValueError, KeyError):
            messages.error(request, 'Product details valid nahi hain.')
    return render(request, 'store/add_product.html', {'categories': Category.objects.all(), 'subcategories': Subcategory.objects.all()})

seller_add_product = add_product

@admin_required
def update_product(request, pk):
    product = get_object_or_404(Product, pk=pk) 
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        subcategory_id = request.POST.get('subcategory') or None
        try:
            discount_percent = int(request.POST.get('discount_percent', 0) or 0)
            if discount_percent < 0 or discount_percent > 100:
                raise ValueError
            price = Decimal(request.POST.get('price', '0'))
            stock = int(request.POST.get('stock', '0'))
            if price < 0 or stock < 0:
                raise ValueError
            subcategory = Subcategory.objects.filter(id=subcategory_id, category_id=category_id).first() if subcategory_id else None
            product.name = request.POST.get('name', '').strip()
            product.price = price
            product.stock = stock
            product.category_id = category_id
            product.subcategory = subcategory
            product.description = request.POST.get('description', '').strip()
            product.discount_percent = discount_percent

            # Flash deal update
            is_flash_deal = request.POST.get('is_flash_deal') == 'on'
            product.is_flash_deal = is_flash_deal
            if is_flash_deal:
                raw_time = request.POST.get('flash_end_time')
                if raw_time and raw_time.strip():
                    parsed = parse_datetime(raw_time.strip())
                    if parsed:
                        if timezone.is_naive(parsed):
                            parsed = timezone.make_aware(parsed)
                        product.flash_end_time = parsed
                    elif not product.flash_end_time:
                        product.flash_end_time = timezone.now() + timedelta(minutes=10)
                elif not product.flash_end_time:
                    product.flash_end_time = timezone.now() + timedelta(minutes=10)
            else:
                product.flash_end_time = None

            if not product.name or not category_id:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, 'Product details valid nahi hain. Discount 0 se 100 ke beech hona chahiye.')
            return redirect('update_product', pk=product.pk)
        
        if request.FILES.get('image'): 
            product.image = request.FILES.get('image')
            
        product.save()

        variant_names = request.POST.getlist('variant_name')
        variant_prices = request.POST.getlist('variant_price')
        variant_stocks = request.POST.getlist('variant_stock')
        if variant_names:
            valid_variants = []
            for v_name, v_price, v_stock in zip(variant_names, variant_prices, variant_stocks):
                if v_name and v_name.strip() and v_price:
                    try:
                        valid_variants.append(ProductVariant(
                            product=product,
                            weight=v_name.strip(),
                            price=Decimal(v_price),
                            stock=int(v_stock or 0)
                        ))
                    except (ValueError, TypeError):
                        pass
            if valid_variants:
                product.variants.all().delete()
                ProductVariant.objects.bulk_create(valid_variants)

        messages.success(request, "Product updated!")
        return redirect('admin_dashboard')

    categories = Category.objects.all()
    subcategories = Subcategory.objects.filter(category_id=product.category_id)
    return render(request, 'store/update_product.html', {
        'product': product,
        'categories': categories,
        'subcategories': subcategories
    })


@admin_required
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST': 
        product.delete()
        messages.success(request, "Product deleted!")
        return redirect('admin_dashboard')
    
    return render(request, 'store/delete_product.html', {'product': product})
    

def search_products(request):
    query = request.GET.get('q','')
    products = Product.objects.none()

    if query:
        products= Product.objects.filter(name__icontains=query)
                                    
    return render(request,'store/search_results.html',{
        'products':products,'query':query })    
        

def add_to_cart(request, product_id):
    if not request.user.is_authenticated:
        next_path = request.get_full_path()
        return redirect(f"/?login_required=1&next={quote(next_path)}")

    product = get_object_or_404(Product, id=product_id)

    cart = request.session.get('cart', {})
    if not isinstance(cart, dict):
        cart = {}

    variant_id = request.GET.get('variant_id') or request.POST.get('variant_id') or request.GET.get('selected_variant')
    variant = None
    variant_name = ""

    # Check flash deal active status
    deal_active = product.is_flash_deal
    deal_ended = False
    if product.is_flash_deal and product.flash_end_time:
        deal_ended = timezone.now() > product.flash_end_time

    if variant_id:
        try:
            variant = ProductVariant.objects.get(id=variant_id, product=product)
            price = float(variant.price)
            variant_name = f" - {variant.weight}"
        except ProductVariant.DoesNotExist:
            variant = None
            price = float(product.discounted_price) if (deal_active and not deal_ended) else float(product.price)
    else:
        if deal_active and not deal_ended:
            price = float(product.discounted_price)
        else:
            price = float(product.price)

    cart_key = f"{product_id}_{variant.id}" if variant else f"{product_id}"
    current_qty = cart.get(cart_key, {}).get('qty', 0)

    available_stock = product.stock
    if variant and variant.stock and variant.stock > 0:
        available_stock = variant.stock

    if available_stock <= 0:
        messages.error(request, f'{product.name} is out of stock!')
        return redirect('cart_view')

    if current_qty + 1 > available_stock:
        messages.error(request, f'Sorry, only {available_stock} items left!')
        return redirect('cart_view')

    cart[cart_key] = {
        'product_id': str(product_id),
        'variant_id': str(variant.id) if variant else None,
        'qty': current_qty + 1,
        'price': price,
        'name': product.name + variant_name,
        'variant_weight': variant.weight if variant else ''
    }

    request.session['cart'] = cart
    request.session.modified = True

    next_url = request.GET.get('next') or request.POST.get('next')
    if (request.method == 'POST' and request.POST.get('action') == 'buy_now') or next_url == '/checkout/' or next_url == 'checkout':
        return redirect('checkout')

    encoded_name = quote(product.name + variant_name)
    return redirect(f"/?added=1&name={encoded_name}")
    
def cart_view(request):
    cart = request.session.get('cart', {})
    if not isinstance(cart, dict):
        cart = {}
        request.session['cart'] = cart

    cart_items = []
    subtotal = Decimal('0')

    for cart_key, item in cart.items():
        
        if isinstance(item, int):
            qty = item
            try:
                product = get_object_or_404(Product, id=int(cart_key))
                price = product.discounted_price
                item_dict = {'qty': qty, 'price': float(price),'original_price':float(product.price), 'product_id': product.id, 'name': product.name}
            except:
                continue
        elif isinstance(item, dict):
            if not item.get('qty') or not item.get('price'):
                continue
            qty = int(item['qty'])
            price = Decimal(str(item['price']))
            item_dict = item
            product = get_object_or_404(Product, id=item_dict.get('product_id', cart_key))
        else:
            continue
        

        item_subtotal = price * qty
        subtotal += item_subtotal

        cart_items.append({
            'key': cart_key,
            'name': item_dict.get('name', product.name),
            'weight': item_dict.get('weight', ''),
            'price': price,
            'qty': qty,
            'subtotal': item_subtotal,
            'image':product.image.url if product.image else '',
            'product': product
        })
    discount_amount = Decimal(request.session.get('discount_amount', '0'))
    discount_code = request.session.get('discount_code', '')
    save10_minimum = Decimal('500')
    save10_eligible = subtotal >= save10_minimum
    if discount_code.upper() == 'SAVE10' and not save10_eligible:
        discount_amount = Decimal('0')
        discount_code = ''
        request.session['discount_amount'] = '0'
        request.session['discount_code'] = ''
    elif discount_code.upper() == 'SAVE10':
        discount_amount = subtotal * Decimal('10') / Decimal('100')
    final_total = subtotal - discount_amount
    if final_total < 0: final_total = Decimal('0')
    
    return render(request, 'store/cart.html', {
            'cart_items': cart_items,
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'final_total': final_total,
            'discount_code': discount_code,
            'save10_minimum': save10_minimum,
            'save10_eligible': save10_eligible,
            'save10_remaining': max(save10_minimum - subtotal, Decimal('0')),
            'save10_applied': discount_code.upper() == 'SAVE10' and discount_amount > 0
        })
    
def update_qty(request, key):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.content_type == 'application/json'
    if request.method == 'POST':
        try:
            new_qty = int(request.POST.get('qty', 1))
            product = get_object_or_404(Product, id=str(key).split('_')[0])
            if new_qty > product.stock:
                error_msg = f'Stock not available. Only {product.stock} in stock'
                if is_ajax:
                    return JsonResponse({'error': error_msg, 'max_stock': product.stock, 'success': False}, status=400)
                messages.error(request, error_msg)
                return redirect('cart_view')

            if new_qty >= 1:
                cart = request.session.get('cart', {})
                item = cart.get(str(key))
                if item is not None:
                    if isinstance(item, int):
                        cart[str(key)] = new_qty
                    elif isinstance(item, dict):
                        item['qty'] = new_qty
                        cart[str(key)] = item
                    request.session['cart'] = cart
                    request.session.modified = True
                    if is_ajax:
                        return JsonResponse({'success': True, 'qty': new_qty, 'max_stock': product.stock})
        except Exception as e:
            if is_ajax:
                return JsonResponse({'error': str(e), 'success': False}, status=400)
    return redirect('cart_view')

def apply_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('coupon_code', '').strip()
        cart = request.session.get('cart', {})
        subtotal = Decimal('0')
        for pid, item in cart.items():
            try:
                product = Product.objects.get(id=int(str(pid).split('_')[0].strip()))
                qty = item.get('qty', 1) if isinstance(item, dict) else item
                price = Decimal(str(item.get('price', product.discounted_price) if isinstance(item, dict) else product.discounted_price))
                subtotal += price * Decimal(str(qty))
            except Exception:
                continue
        try:
            coupon = Coupon.objects.get(code__iexact=code, active=True)
            now = timezone.now()
            if not (coupon.valid_from <= now and (coupon.expired_date is None or now <= coupon.expired_date)):
                raise ValueError('Coupon expired che')
            if code.upper() == 'SAVE10' and subtotal < Decimal('500'):
                raise ValueError(f'SAVE10 unlock karne ke liye ₹{Decimal("500") - subtotal} aur add karein.')
            if subtotal < coupon.min_amount:
                raise ValueError(f'Min order ₹{coupon.min_amount} joiye - Tamaro cart ₹{subtotal} che')
            percent = Decimal('10') if code.upper() == 'SAVE10' else Decimal(str(coupon.discount_percent))
            request.session['discount_amount'] = str(subtotal * percent / Decimal('100'))
            request.session['discount_code'] = coupon.code
            messages.success(request, f'Coupon {code} apply thai gyu! {percent}% OFF')
        except (Coupon.DoesNotExist, ValueError) as error:
            messages.error(request, 'Invalid coupon' if isinstance(error, Coupon.DoesNotExist) else str(error))
            request.session['discount_amount'] = '0'
            request.session['discount_code'] = ''
    return redirect('cart_view')

def update_cart(request, cart_key, action):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.content_type == 'application/json'
    cart = request.session.get('cart', {})
    product = get_object_or_404(Product, id=str(cart_key).split('_')[0])
    current_qty = cart.get(cart_key, 0)
    if isinstance(current_qty, dict):
        current_qty = current_qty.get('qty', 0)
    else:
        current_qty = int(current_qty or 0)

    if action == 'increase':
        if current_qty >= product.stock:
            error_msg = f'Stock not available. Only {product.stock} in stock'
            if is_ajax:
                return JsonResponse({'error': error_msg, 'max_stock': product.stock, 'success': False}, status=400)
            messages.error(request, error_msg)
            return redirect('cart_view')
        
        new_qty = current_qty + 1
        if isinstance(cart.get(cart_key), dict):
            cart[cart_key]['qty'] = new_qty
        else:
            cart[cart_key] = new_qty
        request.session['cart'] = cart
        request.session.modified = True
        if is_ajax:
            return JsonResponse({'success': True, 'qty': new_qty, 'max_stock': product.stock})
        return redirect('cart_view')

    elif action == 'decrease':
        new_qty = current_qty - 1
        if new_qty <= 0:
            cart.pop(cart_key, None)
        else:
            if isinstance(cart.get(cart_key), dict):
                cart[cart_key]['qty'] = new_qty
            else:
                cart[cart_key] = new_qty
        request.session['cart'] = cart
        request.session.modified = True
        if is_ajax:
            return JsonResponse({'success': True, 'qty': max(new_qty, 0), 'max_stock': product.stock})
        return redirect('cart_view')

    elif action in ['edit', 'set'] and cart_key in cart:
        try:
            new_qty = int(request.POST.get('qty', 1))
        except (ValueError, TypeError):
            new_qty = 1

        if new_qty > product.stock:
            error_msg = f'Stock not available. Only {product.stock} in stock'
            if is_ajax:
                return JsonResponse({'error': error_msg, 'max_stock': product.stock, 'success': False}, status=400)
            messages.error(request, error_msg)
            return redirect('cart_view')

        if new_qty <= 0:
            cart.pop(cart_key, None)
        else:
            if isinstance(cart[cart_key], dict):
                cart[cart_key]['qty'] = new_qty
            else:
                cart[cart_key] = new_qty
        request.session['cart'] = cart
        request.session.modified = True
        if is_ajax:
            return JsonResponse({'success': True, 'qty': new_qty, 'max_stock': product.stock})
        return redirect('cart_view')

    elif action == 'remove':
        cart.pop(cart_key, None)
        request.session['cart'] = cart
        request.session.modified = True
        if is_ajax:
            return JsonResponse({'success': True, 'removed': True})
        return redirect('cart_view')

    request.session['cart'] = cart
    request.session.modified = True
    if is_ajax:
        return JsonResponse({'success': True})
    return redirect('cart_view')
@transaction.atomic
@login_required(login_url='/login/')
def checkout(request):
    cart = request.session.get('cart', {})
    if not cart:
        messages.warning(request, 'Cart is empty!')
        return redirect('cart_view')

    cart_items = []
    total = Decimal('0')
    invalid_items = []
    out_of_stock_items = []

    for product_id_str, qty_data in cart.items():
        if isinstance(qty_data, dict):
            qty = int(qty_data.get('qty', 0))
        else:
            qty = int(qty_data)

        if qty <= 0: continue

        try:
            product = Product.objects.get(id=int(product_id_str))
        except Product.DoesNotExist:
            invalid_items.append(product_id_str)
            continue

        if product.stock < qty:
            out_of_stock_items.append({'product': product, 'requested': qty, 'available': product.stock})
            continue

        subtotal = product.discounted_price * qty
        total += subtotal
        cart_items.append({'product': product, 'qty': qty, 'subtotal': subtotal})

    if invalid_items:
        for pid in invalid_items:
            del cart[pid]
        request.session['cart'] = cart
        messages.error(request, 'Some items were removed from cart because they are no longer available.')
        return redirect('cart_view')

    if out_of_stock_items:
        for item in out_of_stock_items:
            messages.error(request, f"{item['product'].name} me sirf {item['available']} stock bacha hai")
        return redirect('cart_view')

    discount = Decimal(request.session.get('discount_amount', '0'))
    discount_code=request.session.get('discount_code','')
    if discount_code.upper() == 'SAVE10':
        if total < Decimal('500'):
            discount = Decimal('0')
            discount_code = ''
            request.session['discount_amount'] = '0'
            request.session['discount_code'] = ''
            messages.warning(request, 'SAVE10 ke liye minimum cart subtotal ₹500 hona chahiye.')
        else:
            discount = total * Decimal('10') / Decimal('100')
    final_total = total - discount
    if final_total < 0: final_total = Decimal('0')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                customer_name = request.POST.get('name', '').strip()
                customer_phone = request.POST.get('phone', '').strip()
                customer_address = request.POST.get('address', '').strip()

                # COD order — cash_received is null until admin/delivery boy records it on bill page
                new_order = Order.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    customer_name=customer_name or 'Guest',
                    customer_phone=customer_phone,
                    total_amount=final_total,
                    paid_amount=Decimal('0'),
                    cash_received=None,
                    discount_code=discount_code
                )
                for item in cart_items:
                    OrderItem.objects.create(
                        order=new_order,
                        product_name=item['product'].name,
                        qty=item['qty'],
                        price=item['product'].discounted_price,
                        final_price=item['product'].discounted_price
                    )
                    product = item['product']
                    product.stock -= item['qty']
                    product.save()

            request.session['last_order_id'] = new_order.id
            request.session['last_order_total'] = str(final_total)
            request.session['last_order_address'] = customer_address
            request.session['last_order_name'] = customer_name or 'Guest'
            request.session['last_order_phone'] = customer_phone

            messages.success(request, f'Order placed successfully! Total ₹{final_total}')
            if 'cart' in request.session:
                del request.session['cart']
            if 'cart_items' in request.session:
                del request.session['cart_items']
            request.session['cart_total'] = 0
            request.session['discount_amount'] = '0'
            request.session['discount_code'] = ''
            request.session.modified = True
            return redirect('order_success')

        except Exception as e:
            messages.error(request, f'Order failed: {e}')
            return redirect('cart_view')

    return render(request, 'store/checkout.html', {
        'cart_items': cart_items,
        'total': total,
        'discount': discount,
        'final_total': final_total,
    })

@login_required(login_url='/login/')
def order_success(request):
    last_order_id = request.session.pop('last_order_id', None)
    last_order_total = request.session.pop('last_order_total', '0')
    last_order_address = request.session.pop('last_order_address', '')
    last_order_name = request.session.pop('last_order_name', '')
    last_order_phone = request.session.pop('last_order_phone', '')
    if 'cart' in request.session:
        del request.session['cart']
    if 'cart_items' in request.session:
        del request.session['cart_items']
    request.session['cart_total'] = 0
    request.session.modified = True
    return render(request, 'store/order_success.html', {
        'last_order_id': last_order_id,
        'last_order_total': last_order_total,
        'last_order_address': last_order_address,
        'last_order_name': last_order_name,
        'last_order_phone': last_order_phone,
    })

@never_cache
@ensure_csrf_cookie
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Check 1: User exist karta hai kya?
        if not User.objects.filter(username=username).exists():
            messages.warning(request, "New user? Please Register first.")
            return redirect('register') 

        # Check 2: Password sahi hai kya?
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session['customer_id'] = user.id  # navbar ke liye
            messages.success(request, f"Welcome back, {username}!")
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('home')
        else:
            messages.error(request, "Wrong Password")

    return render(request, 'store/login.html', {'next': request.GET.get('next', '')})

def logout_view(request):
    logout(request)
    messages.info(request,"You have been logged out.")
    return redirect('home')

def category_view(request,category_id):
    category = Category.objects.get(id=category_id)
    Subcategories=Subcategory.objects.filter(category=category)
    products=Product.objects.filter(category=category)
    return render(request,'store/category.html',{
        'category':category,
        'subcategory':Subcategory,
        'products':products
    })

@login_required(login_url='/login/')
def bill_view(request, order_id=None):
    if order_id:
        order = get_object_or_404(Order, id=order_id)
    else:
        order = Order.objects.last()

    if not order:
        from django.http import HttpResponse
        return HttpResponse("No orders found")

    items = order.items.all()

    if request.method == 'POST':
        if not request.user.is_staff:
            return HttpResponseForbidden("You are not allowed to record payment")
        action = request.POST.get('action', 'edit_prices')

        # --- Action 1: Admin records cash received ---
        if action == 'record_cash':
            raw = request.POST.get('cash_received', '').strip()
            try:
                cash_val = Decimal(raw)
                if cash_val < 0:
                    raise ValueError
            except (ValueError, Exception):
                messages.error(request, 'Cash amount valid positive number hona chahiye.')
                return redirect('bill_detail', order_id=order.id)

            order.cash_received = cash_val
            total = order.total_amount

            if cash_val >= total:
                # PAID IN FULL (or overpaid — change to be returned)
                order.paid_amount = total
                order.save(update_fields=['cash_received', 'paid_amount'])
                change = cash_val - total
                msg = f'Payment recorded: ₹{cash_val} received. PAID IN FULL.'
                if change > 0:
                    msg += f' Return ₹{change} to customer.'
                messages.success(request, msg)
            else:
                # Partial — record what was received, bill stays PENDING
                order.paid_amount = cash_val
                order.save(update_fields=['cash_received', 'paid_amount'])
                messages.warning(request, f'₹{cash_val} received. Bill still PENDING — full amount not collected yet.')
            return redirect('bill_detail', order_id=order.id)

        # --- Action 2: Edit item prices ---
        edited_total = Decimal('0')
        for item in items:
            raw_price = request.POST.get(f'final_price_{item.id}', '')
            try:
                final_price = Decimal(raw_price)
                if final_price < 0:
                    raise ValueError
            except (ArithmeticError, ValueError):
                messages.error(request, 'Price valid positive amount hona chahiye.')
                return redirect('bill_detail', order_id=order.id)
            item.final_price = final_price
            item.save(update_fields=['final_price'])
            edited_total += final_price * item.qty

        order.total_amount = edited_total
        if order.paid_amount > edited_total:
            order.paid_amount = edited_total
        order.save(update_fields=['total_amount', 'paid_amount'])
        messages.success(request, 'Bill prices aur total update ho gaya.')
        return redirect('bill_detail', order_id=order.id)

    # --- Compute payment_status for template: PENDING or PAID ---
    cash = order.cash_received
    total = order.total_amount

    if cash is not None and cash >= total:
        payment_status = 'PAID'
        change_amount = cash - total
    else:
        payment_status = 'PENDING'
        change_amount = Decimal('0')

    cart_items = []
    for item in items:
        cart_items.append({
            'name': item.product_name,
            'qty': item.qty,
            'price': item.bill_price,
            'subtotal': float(item.qty) * float(item.bill_price),
            'id': item.id,
        })

    bill_data = {
        'id': order.id,
        'date': order.created_at,
        'customer_name': order.customer_name,
        'customer_phone': order.customer_phone,
        'cart_items': cart_items,
        'total': order.total_amount,
        'discount': 0,
        'discount_code': order.discount_code,
        'final_total': order.total_amount,
        'cash_received': cash,
        'payment_status': payment_status,
        'change_amount': change_amount,
    }
    is_admin = request.user.is_authenticated and request.user.is_staff
    return render(request, 'store/bill.html', {
        'bill': bill_data,
        'order': order,
        'is_admin': is_admin,
    })

def record_cash_payment(request, order_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("You are not allowed to record payment")
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        amount = request.POST.get('cash_amount') or request.POST.get('cash_received')
        try:
            if amount is not None and str(amount).strip():
                amt_dec = Decimal(str(amount).strip())
                order.cash_collected = True
                order.cash_amount_received = amt_dec
                order.cash_received = amt_dec
                order.paid_amount = amt_dec
                order.cash_collected_at = timezone.now()
                order.cash_collected_by = request.user.username if (request.user and request.user.is_authenticated) else 'Staff'
                order.status = 'Delivered'
                order.payment_status = 'PAID'
                order.save()
                messages.success(request, f'Cash ₹{amt_dec} recorded successfully!')
            else:
                messages.error(request, 'Please enter a valid cash amount.')
        except Exception as e:
            messages.error(request, f'Invalid amount: {e}')

    referer = request.META.get('HTTP_REFERER', '')
    if 'order-success' in referer:
        return redirect('order_success')
    return redirect('bill_detail', order_id=order.id)

def register_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request,"Account create! Please login.")
            return redirect('login')
        else:
            print("FORM ERRORS:",form.errors)
            messages.error(request,"From me kuch galti hai")
    else:
       form = UserCreationForm()
    return render(request,'store/register.html',{'form':form})

def product_detail(request, id):
    product = get_object_or_404(Product, id=id)
    variants = product.variants.all()
    user_rating = None
    if request.user.is_authenticated:
        user_rating = ProductRating.objects.filter(product=product, user=request.user).first()
    recent_ratings = product.ratings.select_related('user').order_by('-created_at')[:10]

    deal_active = product.is_flash_deal
    deal_ended = False
    if product.is_flash_deal and product.flash_end_time:
        deal_ended = timezone.now() > product.flash_end_time

    first_variant = variants.first()
    selected_variant_price = first_variant.price if first_variant else product.price
    discounted_price = product.discounted_price

    return render(request, 'store/product_detail.html', {
        'product': product,
        'variants': variants,
        'user_rating': user_rating,
        'recent_ratings': recent_ratings,
        'rating_choices': [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
        'deal_active': deal_active,
        'deal_ended': deal_ended,
        'discounted_price': discounted_price,
        'selected_variant_price': selected_variant_price,
    })

product_detail_view = product_detail

@login_required(login_url='/login/')
def rate_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        try:
            rating_val = float(request.POST.get('rating', '5.0'))
            if not 0.5 <= rating_val <= 5.0:
                raise ValueError("Rating out of bounds")
            review_text = request.POST.get('review', '').strip()
            ProductRating.objects.update_or_create(
                user=request.user,
                product=product,
                defaults={
                    'rating': rating_val,
                    'review': review_text or None,
                }
            )
            messages.success(request, f"Thank you! You rated {product.name} {rating_val}★.")
        except Exception as e:
            messages.error(request, "Invalid rating value.")
    return redirect('product_detail', id=product.id)

@never_cache
@ensure_csrf_cookie
def admin_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        request.session['admin_user_id'] = request.user.id
        return redirect('admin_dashboard')
    admin_id = request.session.get('admin_user_id')
    if admin_id:
        admin_user = User.objects.filter(id=admin_id, is_staff=True).first()
        if admin_user:
            login(request, admin_user)
            request.session['admin_user_id'] = admin_id
            return redirect('admin_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            request.session['admin_user_id'] = user.id
            LoginLog.objects.create(user=user)
            messages.success(request, f"Welcome to Admin Dashboard, {username}!")
            return redirect('admin_dashboard')
        else:
            messages.error(request, "Invalid admin username or password.")
            return render(request, 'store/admin_login.html')

    return render(request, 'store/admin_login.html')

@admin_required
def admin_logins(request):
    users = User.objects.all().order_by('-last_login')
    total_logins = users.count()
    return render(request, 'store/admin_logins.html', {'users': users, 'total_logins': total_logins})

def forgot_password_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, "User does not exist with that username.")
            return render(request, 'store/forgot_password.html', {'username': username})

        if not new_password:
            messages.error(request, "Password cannot be blank.")
            return render(request, 'store/forgot_password.html', {'username': username})

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'store/forgot_password.html', {'username': username})

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'store/forgot_password.html', {'username': username})

        user.set_password(new_password)
        user.save()
        messages.success(request, "Password reset successfully! Please login with your new password.")
        return redirect('login')

    return render(request, 'store/forgot_password.html')

def admin_forgot_password_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        try:
            user = User.objects.get(username=username)
            if not user.is_staff:
                messages.error(request, "No admin account found with that username.")
                return render(request, 'store/admin_forgot_password.html', {'username': username})
        except User.DoesNotExist:
            messages.error(request, "No admin account found with that username.")
            return render(request, 'store/admin_forgot_password.html', {'username': username})

        if not new_password:
            messages.error(request, "Password cannot be blank.")
            return render(request, 'store/admin_forgot_password.html', {'username': username})

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'store/admin_forgot_password.html', {'username': username})

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'store/admin_forgot_password.html', {'username': username})

        user.set_password(new_password)
        user.save()
        messages.success(request, "Admin password reset successfully! Please login with your new password.")
        return redirect('admin_login')

    return render(request, 'store/admin_forgot_password.html')

def my_orders_view(request):
    if not request.user.is_authenticated:
        orders = Order.objects.none()
    elif request.user.is_staff:
        orders = Order.objects.exclude(status__in=['Delivered', 'Cancelled']).prefetch_related('items').order_by('-created_at')
    else:
        orders = Order.objects.filter(user=request.user).exclude(status__in=['Delivered', 'Cancelled']).prefetch_related('items').order_by('-created_at')
    return render(request, 'store/my_orders.html', {'orders': orders})


@login_required
def my_orders(request):
    return my_orders_view(request)

def delete_bill(request, order_id):
    """DISABLED: This view is intentionally disabled to prevent accidental deletion."""
    messages.error(request, "Order deletion is not allowed. Please contact support if needed.")
    referer = request.META.get('HTTP_REFERER', '')
    if 'my-orders' in referer:
        return redirect('my_orders')
    return redirect('my_bills')



def cancel_order(request, order_id):
    if not request.user.is_authenticated:
        messages.warning(request, "Please login to cancel your order.")
        return redirect('login')

    if request.user.is_staff:
        order = get_object_or_404(Order, id=order_id)
    else:
        order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status not in ['Ordered', 'Packed']:
        messages.error(request, f"Order #{order.id} cannot be cancelled at this stage.")
        return redirect('my_orders')

    if request.method == 'POST':
        order_id_val = order.id
        order.delete()
        messages.success(request, f"Order #{order_id_val} cancelled and removed successfully.")
        return redirect('my_orders')

    return redirect('my_orders')



@login_required
@user_passes_test(is_admin)
def add_category(request):
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            Category.objects.get_or_create(name=name)
            return redirect('admin_dashboard') 
    return render(request, 'store/add_category.html')

@login_required
@user_passes_test(is_admin)
def add_subcategory(request):
    categories = Category.objects.all()
    if request.method == "POST":
        cat_id = request.POST.get("category")
        name = request.POST.get("name")
        if cat_id and name:
            cat = Category.objects.get(id=cat_id)
            Subcategory.objects.get_or_create(category=cat, name=name)
            return redirect('admin_dashboard')
    return render(request, 'store/add_subcategory.html', {'categories': categories})

@login_required
@user_passes_test(is_admin)
def edit_category(request, id):
    category = get_object_or_404(Category, id=id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            category.name = name
            category.save()
            messages.success(request, 'Category update ho gayi.')
            return redirect('admin_dashboard')
        messages.error(request, 'Category name required hai.')
    return render(request, 'store/edit_category.html', {'category': category})

@login_required
@user_passes_test(is_admin)
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Category delete ho gayi.')
        return redirect('admin_dashboard')
    return render(request, 'store/delete_category.html', {'category': category})

@login_required
@user_passes_test(is_admin)
def edit_subcategory(request, id):
    subcategory = get_object_or_404(Subcategory, id=id)
    categories = Category.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_id = request.POST.get('category')
        if name and category_id:
            subcategory.name = name
            subcategory.category_id = category_id
            subcategory.save()
            messages.success(request, 'Subcategory update ho gayi.')
            return redirect('admin_dashboard')
        messages.error(request, 'Subcategory name aur category required hai.')
    return render(request, 'store/edit_subcategory.html', {'subcategory': subcategory, 'categories': categories})

@login_required
@user_passes_test(is_admin)
def delete_subcategory(request, id):
    subcategory = get_object_or_404(Subcategory, id=id)
    if request.method == 'POST':
        subcategory.delete()
        messages.success(request, 'Subcategory delete ho gayi.')
        return redirect('admin_dashboard')
    return render(request, 'store/delete_subcategory.html', {'subcategory': subcategory})

# ---- COUPON DASHBOARD CRUD ----

def dashboard_coupons(request):
    coupons = Coupon.objects.all().order_by('-id')
    return render(request, 'store/dashboard_coupons.html', {'coupons': coupons})

def dashboard_add_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('code','').strip().upper()
        discount = request.POST.get('discount_percent')
        min_amount = request.POST.get('min_amount') or 0
        expired_date=request.POST.get('expired_date') or request.POST.get('valid_to') or None
        valid_from=request.POST.get('valid_from') 
        active = True if request.POST.get('active') else False
        
        
        Coupon.objects.create(code=code, discount_percent=discount, min_amount=min_amount,valid_from=valid_from,expired_date=expired_date, active=active)
        messages.success(request, "Coupon Add ho gaya!")
        return redirect('dashboard_coupons')
    return render(request, 'store/dashboard_add_coupon.html')

def dashboard_edit_coupon(request, id):
    coupon = get_object_or_404(Coupon, id=id)
    if request.method == 'POST':
        coupon.code = request.POST.get('code','').strip().upper()
        coupon.discount_percent = request.POST.get('discount_percent')
        coupon.min_amount = request.POST.get('min_amount') or 0
        coupon.valid_from=request.POST.get('valid_from' )or request.POST.get('valid_to') or  timezone.now()
        coupon.expired_date=request.POST.get('expired_date') or None
        coupon.active = True if request.POST.get('active') else False
        coupon.save()
        messages.success(request, "Coupon Update ho gaya!")
        return redirect('dashboard_coupons')
    return render(request, 'store/dashboard_add_coupon.html', {'coupon': coupon})

def dashboard_delete_coupon(request, id):
    Coupon.objects.get(id=id).delete()
    return redirect('dashboard_coupons')

def admin_logout(request):
    logout(request)
    request.session.flush()
    response = redirect('admin_login')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def customer_logout(request):
    request.session.pop('customer_id', None)
    logout(request)
    messages.info(request, "You have been logged out.")
    response = redirect('home')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response
# --- CUSTOMER SECURITY DECORATOR ---
def customer_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if 'customer_id' not in request.session and not request.user.is_authenticated:
            return redirect('login')
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    return wrapper

@never_cache
@customer_login_required
def my_bills_view(request):
    if not request.user.is_authenticated:
        orders = Order.objects.none()
    elif request.user.is_staff:
        orders = Order.objects.all().prefetch_related('items').order_by('-created_at')
    else:
        orders = Order.objects.filter(user=request.user).prefetch_related('items').order_by('-created_at')
    return render(request, 'store/my_bills.html', {'orders': orders})

@never_cache
@customer_login_required
def my_orders_view(request):
    if not request.user.is_authenticated:
        orders = Order.objects.none()
    elif request.user.is_staff:
        orders = Order.objects.exclude(status__in=['Delivered', 'Cancelled']).prefetch_related('items').order_by('-created_at')
    else:
        orders = Order.objects.filter(user=request.user).exclude(status__in=['Delivered', 'Cancelled']).prefetch_related('items').order_by('-created_at')
    return render(request, 'store/my_orders.html', {'orders': orders})



def get_customer(request):
    if request.user.is_authenticated:
        return request.user
    customer_id = request.session.get('customer_id')
    if customer_id:
        return User.objects.filter(id=customer_id).first()
    return None

@never_cache
def add_to_wishlist(request, product_id):
    user = get_customer(request)
    if not user:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'login_required'})
        next_path = request.META.get('HTTP_REFERER') or '/'
        return redirect(f"/login/?next={quote(next_path)}")

    product = get_object_or_404(Product, id=product_id)
    item = Wishlist.objects.filter(user=user, product=product).first()
    
    if item:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            item.delete()
            count = Wishlist.objects.filter(user=user).count()
            return JsonResponse({'status': 'removed', 'count': count, 'product_id': product_id})
        else:
            messages.info(request, f"{product.name} is already in your wishlist.")
            return redirect(request.META.get('HTTP_REFERER', 'home'))
    else:
        Wishlist.objects.create(user=user, product=product)
        count = Wishlist.objects.filter(user=user).count()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'added', 'count': count, 'product_id': product_id})
        messages.success(request, f"{product.name} added to wishlist!")
        return redirect(request.META.get('HTTP_REFERER', 'home'))

@never_cache
def remove_from_wishlist(request, product_id):
    user = get_customer(request)
    if user:
        Wishlist.objects.filter(user=user, product_id=product_id).delete()
    
    count = Wishlist.objects.filter(user=user).count() if user else 0
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'removed', 'count': count, 'product_id': product_id})
    
    messages.info(request, "Item removed from wishlist.")
    return redirect('wishlist_view')

@never_cache
def wishlist_view(request):
    user = get_customer(request)
    if not user:
        messages.warning(request, "Please login to view your wishlist")
        return redirect('/login/?next=/wishlist/')
    
    items = Wishlist.objects.filter(user=user).select_related('product').order_by('-created_at')
    return render(request, 'store/wishlist.html', {'items': items})

def update_order_status(request, order_id):
    order = Order.objects.get(id=order_id)
    if request.method == "POST":
        new_status = request.POST.get('status') # Packed / Shipped / Delivered
        order.status = new_status
        order.save()
    return redirect('admin_orders') # ya jaha se aayi ho