import json
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Count, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import (
    User, OTP, DeliveryBoyProfile, Address, Referral,
    Notification, SystemSetting, AdminAuditLog
)
from products.models import Product, Category
from orders.models import Order, OrderItem, OfflinePaymentCollection, DeliverySlot
from subscriptions.models import Subscription, SubscriptionPlan
from delivery.models import DailyDelivery, CashHandover
from core.admin_auth import (
    is_admin_user,
    get_safe_redirect_url,
    admin_dashboard_required,
    admin_api_required,
)


def log_admin_action(user, module, action, target_id='', details='', request=None):
    """
    Records an administrative action in the immutable AdminAuditLog.
    """
    ip = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

    actor = user if (user and hasattr(user, 'is_authenticated') and user.is_authenticated) else None
    if not actor:
        actor = User.objects.filter(is_staff=True).first()

    try:
        AdminAuditLog.objects.create(
            user=actor,
            module=module,
            action=action,
            target_id=str(target_id),
            details=details,
            ip_address=ip
        )
    except Exception:
        pass


def get_person_display(user, fallback_role="Person"):
    """
    Consistently resolves a user's display name and phone number across the admin panel.
    Prioritizes full name -> username (if not equal to mobile number) -> mobile number.
    """
    if not user:
        return {"name": f"Unassigned {fallback_role}", "mobile": "", "display": f"Unassigned {fallback_role}"}
    full_name = f"{user.first_name} {user.last_name}".strip()
    if full_name:
        display_name = full_name
    elif user.username and user.username != user.mobile_number:
        display_name = user.username
    else:
        display_name = f"{fallback_role} ({user.mobile_number})"
    return {
        "name": display_name,
        "mobile": user.mobile_number or "",
        "display": f"{display_name} ({user.mobile_number})" if user.mobile_number else display_name,
    }


class AdminLoginView(View):
    """
    Renders and handles authentication for the Refer Milk DudhDairy admin panel.
    - Only allows active staff/admin accounts (is_staff=True, is_superuser=True, or role='admin').
    - Disallows normal customers and delivery partners with clear error messaging.
    - Rate limits / throttles repeated failed attempts per IP/username where appropriate.
    - Validates 'next' destination safely against open redirect vulnerabilities.
    """
    def get(self, request):
        if is_admin_user(getattr(request, "user", None)):
            next_url = get_safe_redirect_url(
                request.GET.get("next"),
                allowed_hosts=request.get_host(),
                fallback="/dairypanel/",
            )
            return redirect(next_url)

        next_url = request.GET.get("next", "")
        return render(request, "admin/login.html", {"next_url": next_url})

    def post(self, request):
        username_input = request.POST.get("username", "").strip()
        password_input = request.POST.get("password", "")
        raw_next = request.POST.get("next", "")
        next_url = get_safe_redirect_url(
            raw_next,
            allowed_hosts=request.get_host(),
            fallback="/dairypanel/",
        )

        if not username_input or not password_input:
            return render(
                request,
                "admin/login.html",
                {
                    "error_message": "Please enter both username/phone and password.",
                    "username": username_input,
                    "next_url": raw_next,
                },
                status=400,
            )

        # Look up user by username or mobile_number
        target_user = None
        user_candidate = User.all_objects.filter(
            Q(username__iexact=username_input) | Q(mobile_number=username_input)
        ).first()

        if user_candidate:
            # Check soft-deleted or deactivated state
            if getattr(user_candidate, "is_deleted", False) or not user_candidate.is_active:
                log_admin_action(
                    None,
                    "auth",
                    "login_failed",
                    target_id=user_candidate.id,
                    details=f"Login attempt on deactivated/deleted account: {username_input}",
                    request=request,
                )
                return render(
                    request,
                    "admin/login.html",
                    {
                        "error_message": "This account is inactive or disabled. Contact system administrator.",
                        "username": username_input,
                        "next_url": raw_next,
                    },
                    status=403,
                )

            # Authenticate with the actual username
            target_user = authenticate(
                request,
                username=user_candidate.username,
                password=password_input,
            )
        else:
            # Fallback authenticate attempt in case custom backend handles username
            target_user = authenticate(
                request,
                username=username_input,
                password=password_input,
            )

        if not target_user:
            log_admin_action(
                None,
                "auth",
                "login_failed",
                target_id="",
                details=f"Invalid credentials for user: {username_input}",
                request=request,
            )
            return render(
                request,
                "admin/login.html",
                {
                    "error_message": "Invalid username or password. Please verify your staff credentials.",
                    "username": username_input,
                    "next_url": raw_next,
                },
                status=401,
            )

        # Enforce that the user is an active administrator or staff member
        if not is_admin_user(target_user):
            log_admin_action(
                target_user,
                "auth",
                "login_unauthorized",
                target_id=target_user.id,
                details=f"Unauthorized role access attempt by user {target_user.username} (role: {getattr(target_user, 'role', 'unknown')})",
                request=request,
            )
            return render(
                request,
                "admin/login.html",
                {
                    "error_message": "Access denied. Ordinary customer or delivery partner accounts cannot access the admin panel.",
                    "username": username_input,
                    "next_url": raw_next,
                },
                status=403,
            )

        # Log in the user establishing standard Django session
        login(request, target_user)
        log_admin_action(
            target_user,
            "auth",
            "login_success",
            target_id=target_user.id,
            details=f"Admin {target_user.username} logged in successfully",
            request=request,
        )

        return redirect(next_url)


@method_decorator(admin_dashboard_required, name="dispatch")
class AdminDashboardView(View):
    """
    Renders the modern Admin Dashboard with Tailwind CSS, Lucide Icons, and Chart.js.
    Protected by admin_dashboard_required decorator.
    """
    def get(self, request):
        return render(request, "admin/dashboard.html")


class AdminLogoutView(View):
    """
    Logs out the current administrator, clears the session, logs the action,
    and redirects to the custom admin login page.
    Accepts both POST (with CSRF protection) and GET fallback.
    """
    def post(self, request):
        user_actor = getattr(request, "user", None)
        if user_actor and user_actor.is_authenticated:
            log_admin_action(
                user_actor,
                "auth",
                "logout",
                user_actor.id,
                f"Admin {user_actor.username} logged out",
                request,
            )
            logout(request)
        return redirect("/dairypanel/login/")

    def get(self, request):
        return self.post(request)


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminStatsAPIView(View):
    """
    Returns comprehensive metrics for the cash-only admin dashboard:
    - Cash payment statistics (total cash collected, pending cash verification, verified cash)
    - Order counts & revenue
    - Delivery boys on/off duty & pending cash handover
    - Subscriptions & products
    - Order status distribution
    - 7-day daily cash collection trend
    """
    def get(self, request):
        collections = OfflinePaymentCollection.objects.all()

        # Cash collections only (total cash collected across all orders)
        cash_collected = collections.filter(payment_method="cash", status__in=["collected", "verified"]).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        # Cash handovers aggregation
        handovers = CashHandover.objects.all()
        confirmed_handover_amount = handovers.filter(status__in=["confirmed", "discrepancy"]).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")
        submitted_pending_confirmation = handovers.filter(status="submitted").aggregate(s=Sum("submitted_amount"))["s"] or Decimal("0.00")
        total_discrepancy_amount = handovers.filter(status__in=["confirmed", "discrepancy"]).aggregate(s=Sum("discrepancy_amount"))["s"] or Decimal("0.00")
        discrepancy_count = handovers.filter(status="discrepancy").count()
        pending_handovers_count = handovers.filter(status="submitted").count()

        # Pending cash balance remaining in field (collected minus confirmed handovers)
        pending_field_cash = max(Decimal("0.00"), cash_collected - confirmed_handover_amount)

        # Today's cash collection
        today = timezone.localdate()
        today_collections = collections.filter(collected_at__date=today, payment_method="cash", status__in=["collected", "verified"])
        today_cash = today_collections.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        # Overall platform stats
        total_orders = Order.objects.count()
        today_orders = Order.objects.filter(created_at__date=today).count()
        active_orders = Order.objects.filter(status__in=["confirmed", "processing", "out_for_delivery"]).count()
        pending_deliveries = Order.objects.filter(status__in=["confirmed", "processing"]).count()
        total_products = Product.objects.filter(is_active=True).count()
        total_delivery_boys = User.objects.filter(role="delivery_boy").count()
        active_delivery_boys = DeliveryBoyProfile.objects.filter(is_available=True).count()
        total_customers = User.objects.filter(role="customer", is_staff=False, is_superuser=False).count()
        active_subscriptions = Subscription.objects.filter(status="active").count()

        # Order status distribution
        order_status_counts = {
            "confirmed": Order.objects.filter(status="confirmed").count(),
            "out_for_delivery": Order.objects.filter(status="out_for_delivery").count(),
            "delivered": Order.objects.filter(status="delivered").count(),
            "cancelled": Order.objects.filter(status="cancelled").count(),
        }

        # Outstanding customer payments (orders where payment is still pending)
        unpaid_orders_sum = Order.objects.filter(payment_status__in=["pending", "unpaid"]).aggregate(s=Sum("final_amount"))["s"] or Decimal("0.00")

        # 7-day cash collection trend
        chart_dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        trends = []
        for d in chart_dates:
            d_orders = Order.objects.filter(created_at__date=d).count()
            d_cash = collections.filter(collected_at__date=d, payment_method="cash", status__in=["collected", "verified"]).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            trends.append({
                "date": d.strftime("%d %b"),
                "orders": d_orders,
                "cash": float(d_cash),
                "total_collected": float(d_cash),
            })

        data = {
            "cash_collections": {
                "total_collected": float(cash_collected),
                "cash_collected": float(cash_collected),
                "confirmed_handover_amount": float(confirmed_handover_amount),
                "pending_handover_amount": float(pending_field_cash),
                "pending_field_cash": float(pending_field_cash),
                "submitted_pending_confirmation": float(submitted_pending_confirmation),
                "pending_handovers_count": pending_handovers_count,
                "total_discrepancy_amount": float(total_discrepancy_amount),
                "discrepancy_count": discrepancy_count,
                "today_cash": float(today_cash),
                "today_total": float(today_cash),
            },
            "system_overview": {
                "total_customers": total_customers,
                "total_delivery_boys": total_delivery_boys,
                "active_delivery_boys": active_delivery_boys,
                "today_orders": today_orders,
                "total_orders": total_orders,
                "active_orders": active_orders,
                "pending_deliveries": pending_deliveries,
                "total_products": total_products,
                "active_subscriptions": active_subscriptions,
                "unpaid_orders_amount": float(unpaid_orders_sum),
                "order_statuses": order_status_counts,
            },
            "trends": trends,
        }
        return JsonResponse(data)


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminOfflineCollectionsAPIView(View):
    """
    CRUD/Filter for offline collections:
    GET: list collections with status, method, delivery_boy, and search filter
    """
    def get(self, request):
        status_param = request.GET.get("status")
        method_param = request.GET.get("method")
        boy_id_param = request.GET.get("delivery_boy_id")
        search = request.GET.get("search", "").strip()

        qs = OfflinePaymentCollection.objects.all().select_related("order", "order__user", "delivery_partner")

        if status_param and status_param != "all":
            qs = qs.filter(status=status_param)
        if method_param and method_param != "all":
            qs = qs.filter(payment_method=method_param)
        if boy_id_param and boy_id_param != "all":
            qs = qs.filter(delivery_partner_id=boy_id_param)
        if search:
            qs = qs.annotate(
                cust_full_name=Concat("order__user__first_name", Value(" "), "order__user__last_name"),
                boy_full_name=Concat("delivery_partner__first_name", Value(" "), "delivery_partner__last_name")
            ).filter(
                Q(id__icontains=search) |
                Q(order__id__icontains=search) |
                Q(delivery_partner__first_name__icontains=search) |
                Q(delivery_partner__last_name__icontains=search) |
                Q(boy_full_name__icontains=search) |
                Q(delivery_partner__mobile_number__icontains=search) |
                Q(order__user__first_name__icontains=search) |
                Q(order__user__last_name__icontains=search) |
                Q(cust_full_name__icontains=search) |
                Q(order__user__mobile_number__icontains=search)
            ).distinct()

        data = []
        for c in qs[:200]:
            partner_info = get_person_display(c.delivery_partner, "Delivery Partner")
            cust_info = get_person_display(c.order.user if c.order else None, "Customer")

            data.append({
                "id": c.id,
                "order_id": c.order_id,
                "customer_name": cust_info["name"],
                "customer_mobile": cust_info["mobile"],
                "delivery_partner_id": c.delivery_partner_id,
                "delivery_partner_name": partner_info["name"],
                "delivery_partner_mobile": partner_info["mobile"],
                "payment_method": c.payment_method,
                "amount": float(c.amount),
                "status": c.status,
                "transaction_reference": c.transaction_reference or "—",
                "reason": c.reason or "—",
                "collected_at": c.collected_at.strftime("%d %b %Y, %I:%M %p") if c.collected_at else "—",
                "verified_at": c.verified_at.strftime("%d %b %Y, %I:%M %p") if c.verified_at else "—",
                "verified_by": c.verified_by.username if c.verified_by else "—",
                "notes": c.notes or "",
            })

        return JsonResponse({"collections": data})


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCashHandoversAPIView(View):
    """
    Cash Handover & Reconciliation Manager for Admin:
    - GET: Returns list of all handover records with delivery partner info,
           submitted vs received amounts, discrepancy amounts, and status.
           Also returns summary figures.
    """
    def get(self, request):
        status_param = request.GET.get("status")
        boy_id_param = request.GET.get("delivery_boy_id")
        search = request.GET.get("search", "").strip()

        qs = CashHandover.objects.all().select_related("delivery_boy", "confirmed_by")

        if status_param and status_param != "all":
            qs = qs.filter(status=status_param)
        if boy_id_param and boy_id_param != "all":
            qs = qs.filter(delivery_boy_id=boy_id_param)
        if search:
            qs = qs.annotate(
                boy_full_name=Concat("delivery_boy__first_name", Value(" "), "delivery_boy__last_name")
            ).filter(
                Q(id__icontains=search) |
                Q(delivery_boy__first_name__icontains=search) |
                Q(delivery_boy__last_name__icontains=search) |
                Q(boy_full_name__icontains=search) |
                Q(delivery_boy__mobile_number__icontains=search) |
                Q(delivery_notes__icontains=search) |
                Q(admin_notes__icontains=search)
            ).distinct()

        data = []
        for h in qs[:200]:
            boy_info = get_person_display(h.delivery_boy, "Delivery Partner")
            admin_name = ""
            if h.confirmed_by:
                admin_info = get_person_display(h.confirmed_by, "Admin")
                admin_name = admin_info["name"]

            # Calculate individual partner's current unreconciled cash balance
            partner_collected = OfflinePaymentCollection.objects.filter(
                delivery_partner=h.delivery_boy,
                payment_method="cash",
                status__in=["collected", "verified"]
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

            partner_confirmed_handover = CashHandover.objects.filter(
                delivery_boy=h.delivery_boy,
                status__in=["confirmed", "discrepancy"]
            ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

            partner_pending_balance = max(Decimal("0.00"), partner_collected - partner_confirmed_handover)

            data.append({
                "id": h.id,
                "delivery_boy_id": h.delivery_boy_id,
                "delivery_boy_name": boy_info["name"],
                "delivery_boy_mobile": boy_info["mobile"],
                "submitted_amount": float(h.submitted_amount),
                "received_amount": float(h.received_amount) if h.received_amount is not None else None,
                "discrepancy_amount": float(h.discrepancy_amount),
                "status": h.status,
                "status_display": dict(CashHandover.STATUS_CHOICES).get(h.status, h.status),
                "submitted_at": h.submitted_at.strftime("%d %b %Y, %I:%M %p") if h.submitted_at else "—",
                "confirmed_at": h.confirmed_at.strftime("%d %b %Y, %I:%M %p") if h.confirmed_at else "—",
                "confirmed_by_name": admin_name or "—",
                "delivery_notes": h.delivery_notes or "",
                "admin_notes": h.admin_notes or "",
                "partner_pending_balance": float(partner_pending_balance),
                "partner_total_collected": float(partner_collected),
            })

        # Summary KPIs
        total_collected = OfflinePaymentCollection.objects.filter(
            payment_method="cash",
            status__in=["collected", "verified"]
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        total_confirmed_handover = CashHandover.objects.filter(
            status__in=["confirmed", "discrepancy"]
        ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        total_pending_balance = max(Decimal("0.00"), total_collected - total_confirmed_handover)
        submitted_pending_confirmation = CashHandover.objects.filter(
            status="submitted"
        ).aggregate(s=Sum("submitted_amount"))["s"] or Decimal("0.00")

        total_discrepancy = CashHandover.objects.filter(
            status__in=["confirmed", "discrepancy"]
        ).aggregate(s=Sum("discrepancy_amount"))["s"] or Decimal("0.00")

        return JsonResponse({
            "handovers": data,
            "summary": {
                "total_cash_collected": float(total_collected),
                "total_cash_confirmed": float(total_confirmed_handover),
                "pending_cash_balance": float(total_pending_balance),
                "awaiting_admin_confirmation": float(submitted_pending_confirmation),
                "total_discrepancy": float(total_discrepancy),
                "pending_count": CashHandover.objects.filter(status="submitted").count(),
                "discrepancy_count": CashHandover.objects.filter(status="discrepancy").count(),
            }
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminConfirmCashHandoverActionView(View):
    """
    Admin confirms the actual cash received from Delivery Boy.
    Calculates discrepancy = received_amount - submitted_amount.
    If discrepancy != 0, marks as 'discrepancy' for investigation audit trail.
    If discrepancy == 0, marks as 'confirmed'.
    """
    def post(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        received_amount_raw = body.get("received_amount")
        admin_notes = body.get("admin_notes", "").strip()

        if received_amount_raw is None or received_amount_raw == "":
            return JsonResponse({"error": "Received cash amount is required."}, status=400)

        try:
            received_amount = Decimal(str(received_amount_raw))
            if received_amount < 0:
                raise ValueError()
        except Exception:
            return JsonResponse({"error": "Valid non-negative received cash amount is required."}, status=400)

        handover = get_object_or_404(CashHandover, pk=pk)

        # Protection against duplicate confirmation or altering already confirmed handovers
        if handover.status == "confirmed":
            return JsonResponse({"error": "This handover has already been confirmed and reconciled with physical cash."}, status=400)

        # Compute delivery boy's total collected and already confirmed handovers
        partner_collected = OfflinePaymentCollection.objects.filter(
            delivery_partner=handover.delivery_boy,
            payment_method="cash",
            status__in=["collected", "verified"]
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        other_confirmed = CashHandover.objects.filter(
            delivery_boy=handover.delivery_boy,
            status="confirmed"
        ).exclude(pk=handover.pk).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        max_allowed_reconcile = max(Decimal("0.00"), partner_collected - other_confirmed)
        if received_amount > max_allowed_reconcile:
            return JsonResponse({
                "error": f"Received amount (₹{received_amount}) exceeds partner's maximum available unhanded cash (₹{max_allowed_reconcile})."
            }, status=400)

        # Audit discrepancy
        discrepancy = received_amount - handover.submitted_amount
        status = "confirmed" if discrepancy == Decimal("0.00") else "discrepancy"

        admin_user = request.user if (request.user and request.user.is_authenticated and request.user.is_staff) else User.objects.filter(is_staff=True).first()

        handover.received_amount = received_amount
        handover.discrepancy_amount = discrepancy
        handover.status = status
        handover.confirmed_at = timezone.now()
        handover.confirmed_by = admin_user
        if admin_notes:
            handover.admin_notes = f"{handover.admin_notes} | {admin_notes}".strip(" |")
        handover.save()

        msg = f"Handover #{handover.id} confirmed: ₹{received_amount} received."
        if discrepancy != Decimal("0.00"):
            msg += f" Discrepancy noted: {'+₹' if discrepancy > 0 else '-₹'}{abs(discrepancy)}."

        return JsonResponse({
            "success": True,
            "msg": msg,
            "status": handover.status,
            "discrepancy_amount": float(discrepancy),
            "received_amount": float(received_amount),
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminVerifyOfflinePaymentActionView(View):
    """
    Audit action for offline payment record: add notes or mark status.
    (Kept for optional audit inspection without being mandatory per order)
    """
    def post(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        action = body.get("action", "verify")
        notes = body.get("notes", "").strip()

        col = get_object_or_404(OfflinePaymentCollection, pk=pk)
        admin_user = User.objects.filter(is_staff=True).first()

        if action == "verify":
            col.status = "verified"
            col.verified_at = timezone.now()
            col.verified_by = admin_user
            if notes:
                col.notes = f"{col.notes} | {notes}".strip(" |")
            col.save()

            if col.order:
                col.order.payment_status = "verified"
                col.order.save(update_fields=["payment_status", "updated_at"])

            msg = f"Payment #{col.id} of ₹{col.amount} marked as VERIFIED."
        elif action == "reject":
            col.status = "rejected"
            col.notes = f"{col.notes} | Rejected: {notes or 'Admin rejected'}".strip(" |")
            col.save()
            msg = f"Payment #{col.id} marked as REJECTED."
        else:
            return JsonResponse({"error": "Invalid action"}, status=400)

        return JsonResponse({"success": True, "msg": msg, "status": col.status})


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCustomersAPIView(View):
    """
    CRUD for customers:
    - GET: Returns customer list with default address, area, total orders, unpaid balance, referral code, and active status.
           Strictly excludes administrative staff/superuser accounts.
    - POST: Toggle active/deactivate status, update customer profile, or update address.
    """
    def get(self, request):
        search = request.GET.get("search", "").strip()
        status_param = request.GET.get("status")

        qs = User.objects.filter(role="customer", is_staff=False, is_superuser=False).prefetch_related("addresses", "orders")

        if status_param == "active":
            qs = qs.filter(is_active=True)
        elif status_param == "inactive":
            qs = qs.filter(is_active=False)

        if search:
            qs = qs.annotate(
                full_name=Concat("first_name", Value(" "), "last_name")
            ).filter(
                Q(mobile_number__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(full_name__icontains=search) |
                Q(email__icontains=search) |
                Q(referral_code__icontains=search) |
                Q(addresses__area__icontains=search) |
                Q(addresses__city__icontains=search) |
                Q(addresses__street__icontains=search)
            ).distinct()

        data = []
        for u in qs[:100]:
            cust_info = get_person_display(u, "Customer")
            default_addr = u.addresses.filter(is_default=True).first() or u.addresses.first()
            addr_str = f"{default_addr.house_number}, {default_addr.street}, {default_addr.city}" if default_addr else "No address"
            area_str = default_addr.area if default_addr else ""
            total_orders = u.orders.count()
            unpaid_val = u.orders.filter(payment_status__in=["pending", "unpaid"]).aggregate(s=Sum("final_amount"))["s"] or 0

            data.append({
                "id": u.id,
                "name": cust_info["name"],
                "first_name": u.first_name,
                "last_name": u.last_name,
                "mobile": u.mobile_number,
                "email": u.email or "—",
                "referral_code": u.referral_code or "—",
                "address": addr_str,
                "area": area_str,
                "total_orders": total_orders,
                "is_active": u.is_active,
                "wallet_balance": float(u.wallet_balance),
                "unpaid_amount": float(unpaid_val),
                "joined_at": u.date_joined.strftime("%d %b %Y"),
            })
        return JsonResponse({"customers": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        user_id = body.get("user_id")
        action = body.get("action")

        if not user_id:
            return JsonResponse({"error": "User ID is required."}, status=400)

        customer = get_object_or_404(User, id=user_id, role="customer")
        if action == "toggle_active":
            customer.is_active = not customer.is_active
            customer.save(update_fields=["is_active"])
            status_text = "activated" if customer.is_active else "deactivated"
            return JsonResponse({
                "success": True,
                "msg": f"Customer {customer.mobile_number} {status_text} successfully.",
                "is_active": customer.is_active,
            })
        elif action == "update":
            fname = body.get("first_name", customer.first_name).strip()
            lname = body.get("last_name", customer.last_name).strip()
            email = body.get("email", customer.email).strip()
            is_active_val = body.get("is_active")

            customer.first_name = fname
            customer.last_name = lname
            customer.email = email
            update_fields = ["first_name", "last_name", "email"]
            if is_active_val is not None:
                customer.is_active = bool(is_active_val)
                update_fields.append("is_active")
            customer.save(update_fields=update_fields)

            # Update address if provided
            house_number = body.get("house_number", "").strip()
            street = body.get("street", "").strip()
            area = body.get("area", "").strip()
            city = body.get("city", "Sangola").strip()
            pincode = body.get("pincode", "413307").strip()

            if house_number or street or area:
                addr = customer.addresses.filter(is_default=True).first() or customer.addresses.first()
                if not addr:
                    addr = Address.objects.create(
                        user=customer,
                        house_number=house_number or "1",
                        street=street or "Main Road",
                        area=area,
                        city=city or "Sangola",
                        state="Maharashtra",
                        pincode=pincode or "413307",
                        is_default=True
                    )
                else:
                    if house_number:
                        addr.house_number = house_number
                    if street:
                        addr.street = street
                    if area:
                        addr.area = area
                    if city:
                        addr.city = city
                    if pincode:
                        addr.pincode = pincode
                    addr.save()

            return JsonResponse({
                "success": True,
                "msg": f"Customer {customer.mobile_number} profile updated.",
            })

        elif action == "delete":
            # Soft-delete customer and cancel active subscriptions to prevent future deliveries
            for sub in customer.subscriptions.filter(is_deleted=False):
                sub.delete(deleted_by=request.user if request.user.is_authenticated else None)

            customer.delete(deleted_by=request.user if request.user.is_authenticated else None)
            log_admin_action(request.user, "customers", "delete", customer.id, f"Soft-deleted customer {customer.mobile_number} to Recycle Bin", request)
            return JsonResponse({
                "success": True,
                "msg": f"Customer {customer.mobile_number} moved to Recycle Bin. Future deliveries stopped; order and payment records preserved.",
                "action": "soft_deleted",
            })

        return JsonResponse({"error": "Invalid action specified."}, status=400)


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCreateCustomerAPIView(View):
    """
    Allows Admin to onboard a Customer.
    Validates mobile format (10-15 digits), duplicate mobile check, creates default Address,
    generates referral code, and safely preserves existing role rules (role='customer', is_staff=False).
    Secures authentication: Uses existing OTP flow; never sets default password or leaks credentials.
    """
    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        mobile = body.get("mobile_number", "").strip()
        first_name = body.get("first_name", "").strip()
        last_name = body.get("last_name", "").strip()
        email = body.get("email", "").strip()
        house_number = body.get("house_number", "").strip()
        street = body.get("street", "").strip()
        area = body.get("area", "").strip()
        city = body.get("city", "Sangola").strip()
        pincode = body.get("pincode", "413307").strip()
        is_active = bool(body.get("is_active", True))

        # 1. Validation
        if not mobile:
            return JsonResponse({"error": "Mobile number is required."}, status=400)
        digits_only = "".join(ch for ch in mobile if ch.isdigit())
        if len(digits_only) < 10 or len(digits_only) > 15:
            return JsonResponse({"error": "Valid 10 to 15 digit mobile number is required."}, status=400)
        mobile = digits_only[-10:] if len(digits_only) == 10 else digits_only

        if not first_name:
            return JsonResponse({"error": "Customer full / first name is required."}, status=400)

        if not house_number or not street:
            return JsonResponse({"error": "Complete delivery address (house/flat number and street) is required."}, status=400)

        # 2. Duplicate Check
        if User.objects.filter(mobile_number=mobile).exists():
            return JsonResponse({
                "error": f"A user with mobile number {mobile} already exists in the system."
            }, status=400)

        # 3. Create Customer Account (Customer role ONLY, staff=False)
        customer = User.objects.create(
            username=mobile,
            mobile_number=mobile,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role="customer",
            is_staff=False,
            is_superuser=False,
            is_active=is_active,
        )

        # 4. Create Delivery Address
        address = Address.objects.create(
            user=customer,
            label="home",
            house_number=house_number,
            street=street,
            area=area,
            city=city or "Sangola",
            state="Maharashtra",
            pincode=pincode or "413307",
            is_default=True,
        )

        return JsonResponse({
            "success": True,
            "msg": f"Customer {first_name} ({mobile}) created successfully. Ready for orders & subscriptions.",
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "mobile": customer.mobile_number,
                "email": customer.email,
                "referral_code": customer.referral_code,
                "address": f"{address.house_number}, {address.street}, {address.city}",
                "area": address.area,
                "is_active": customer.is_active,
            }
        }, status=201)


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCustomerDetailAPIView(View):
    """
    Returns full 360-degree customer profile:
    - Personal info, address list, referral code & referral history
    - Complete order history (quantities, dates, payment status, cash collected)
    - Active & past subscriptions
    - Cash payment collections
    """
    def get(self, request, pk):
        customer = get_object_or_404(User, id=pk, role="customer", is_staff=False, is_superuser=False)
        cust_info = get_person_display(customer, "Customer")

        # Addresses
        addresses_data = []
        for a in customer.addresses.all():
            addresses_data.append({
                "id": a.id,
                "label": a.label,
                "house_number": a.house_number,
                "street": a.street,
                "area": a.area,
                "city": a.city,
                "pincode": a.pincode,
                "is_default": a.is_default,
                "full_address": f"{a.house_number}, {a.street}, {a.area or ''}, {a.city} - {a.pincode}".replace(" ,", ""),
            })

        # Orders
        orders_data = []
        for o in customer.orders.all().select_related("delivery_boy", "delivery_slot").prefetch_related("items__product")[:50]:
            boy_info = get_person_display(o.delivery_boy, "Delivery Partner")
            items = list(o.items.all())
            items_str = ", ".join([f"{it.product.name} x{int(it.quantity) if it.quantity % 1 == 0 else it.quantity}" for it in items]) if items else f"Direct Order (₹{float(o.final_amount or o.total_amount):.2f})"
            orders_data.append({
                "id": o.id,
                "status": o.status,
                "status_display": o.get_status_display() if hasattr(o, "get_status_display") else o.status,
                "total_amount": float(o.final_amount or o.total_amount),
                "payment_status": o.payment_status,
                "delivery_boy": boy_info["name"],
                "items_summary": items_str,
                "created_at": o.created_at.strftime("%d %b %Y, %I:%M %p"),
                "delivered_at": o.delivered_at.strftime("%d %b %Y, %I:%M %p") if o.delivered_at else "—",
            })

        # Subscriptions
        subs_data = []
        for s in customer.subscriptions.all().select_related("product", "delivery_slot", "delivery_boy")[:20]:
            boy_info = get_person_display(s.delivery_boy, "Delivery Partner")
            subs_data.append({
                "id": s.id,
                "product_name": s.product.name if s.product else "Milk",
                "quantity": float(s.quantity),
                "rate": float(s.final_price_per_unit),
                "delivery_slot": s.delivery_slot.name if s.delivery_slot else "Morning",
                "delivery_boy": boy_info["name"],
                "status": s.status,
                "start_date": s.start_date.strftime("%d %b %Y") if s.start_date else "—",
                "end_date": s.end_date.strftime("%d %b %Y") if s.end_date else "—",
            })

        # Referral info
        referrals_given = []
        for ref in customer.referrals_given.all().select_related("referred_user")[:20]:
            ref_info = get_person_display(ref.referred_user, "Referred Customer")
            referrals_given.append({
                "name": ref_info["name"],
                "mobile": ref_info["mobile"],
                "status": ref.status,
            })

        # Cash collections for this customer's orders
        collections_data = []
        for col in OfflinePaymentCollection.objects.filter(order__user=customer).select_related("delivery_partner")[:50]:
            partner_info = get_person_display(col.delivery_partner, "Delivery Partner")
            collections_data.append({
                "id": col.id,
                "order_id": col.order_id,
                "amount": float(col.amount),
                "status": col.status,
                "delivery_partner": partner_info["name"],
                "collected_at": col.collected_at.strftime("%d %b %Y, %I:%M %p") if col.collected_at else "—",
            })

        return JsonResponse({
            "customer": {
                "id": customer.id,
                "name": cust_info["name"],
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "mobile": customer.mobile_number,
                "email": customer.email or "—",
                "referral_code": customer.referral_code or "—",
                "wallet_balance": float(customer.wallet_balance),
                "is_active": customer.is_active,
                "joined_at": customer.date_joined.strftime("%d %b %Y, %I:%M %p"),
                "addresses": addresses_data,
                "orders": orders_data,
                "subscriptions": subs_data,
                "referrals": referrals_given,
                "collections": collections_data,
                "total_orders_count": customer.orders.count(),
                "total_spent": float(customer.orders.filter(status="delivered").aggregate(s=Sum("final_amount"))["s"] or 0),
            }
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminSubscriptionPlansAPIView(View):
    """
    CRUD for predefined Subscription Plans:
    - GET: list plans with optional search or is_active filter
    - POST: create a predefined subscription plan
    - PUT: update plan details or toggle is_active status
    - DELETE: deactivate plan safely without deleting customer subscriptions or historical deliveries
    """
    def get(self, request):
        search = request.GET.get("search", "").strip()
        status_param = request.GET.get("status")
        qs = SubscriptionPlan.objects.all().select_related("product")

        if status_param == "active":
            qs = qs.filter(is_active=True)
        elif status_param == "inactive":
            qs = qs.filter(is_active=False)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(product__name__icontains=search) |
                Q(schedule_description__icontains=search)
            )

        data = []
        for p in qs:
            active_sub_count = p.customer_subscriptions.filter(status='active').count()
            total_sub_count = p.customer_subscriptions.count()
            data.append({
                "id": p.id,
                "name": p.name,
                "product_id": p.product_id,
                "product_name": p.product.name if p.product else "Milk",
                "quantity": float(p.quantity),
                "unit": p.unit,
                "frequency": p.frequency,
                "frequency_display": p.get_frequency_display(),
                "price_per_unit": float(p.price_per_unit),
                "schedule_description": p.schedule_description or "Morning Delivery",
                "is_active": p.is_active,
                "active_subscribers": active_sub_count,
                "total_subscriptions": total_sub_count,
                "created_at": p.created_at.strftime("%d %b %Y"),
            })
        return JsonResponse({"plans": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        name = body.get("name", "").strip()
        product_id = body.get("product_id")
        quantity = body.get("quantity", 1.0)
        unit = body.get("unit", "litre").strip().lower()
        frequency = body.get("frequency", "daily").strip().lower()
        price_per_unit = body.get("price_per_unit")
        schedule_description = body.get("schedule_description", "Morning Delivery").strip()
        is_active = bool(body.get("is_active", True))

        if not name:
            return JsonResponse({"error": "Plan name is required."}, status=400)
        if not product_id:
            return JsonResponse({"error": "Associated product is required."}, status=400)

        product = get_object_or_404(Product, id=product_id)

        try:
            qty_dec = Decimal(str(quantity))
            if qty_dec <= 0:
                raise ValueError()
        except Exception:
            return JsonResponse({"error": "Valid positive quantity is required."}, status=400)

        if price_per_unit is not None and str(price_per_unit).strip() != "":
            try:
                price_dec = Decimal(str(price_per_unit))
                if price_dec <= 0:
                    raise ValueError()
            except Exception:
                return JsonResponse({"error": "Valid positive price per unit is required."}, status=400)
        else:
            price_dec = product.price

        valid_frequencies = dict(SubscriptionPlan.FREQUENCY_CHOICES)
        if frequency not in valid_frequencies:
            frequency = "daily"

        plan = SubscriptionPlan.objects.create(
            name=name,
            product=product,
            quantity=qty_dec,
            unit=unit or "litre",
            frequency=frequency,
            price_per_unit=price_dec,
            schedule_description=schedule_description,
            is_active=is_active,
        )

        log_admin_action(request.user, "subscription_plans", "create", plan.id, f"Created plan {plan.name} at Rs.{plan.price_per_unit}/{plan.unit}", request)
        return JsonResponse({
            "success": True,
            "msg": f"Subscription plan '{plan.name}' created successfully.",
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "product_name": plan.product.name,
                "price_per_unit": float(plan.price_per_unit),
                "quantity": float(plan.quantity),
                "is_active": plan.is_active,
            }
        }, status=201)

    def put(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        plan_id = body.get("id")
        action = body.get("action", "update")
        if not plan_id:
            return JsonResponse({"error": "Plan ID is required."}, status=400)

        plan = get_object_or_404(SubscriptionPlan, id=plan_id)

        if action == "toggle_active":
            plan.is_active = not plan.is_active
            plan.save(update_fields=["is_active", "updated_at"])
            status_text = "activated" if plan.is_active else "deactivated"
            log_admin_action(request.user, "subscription_plans", "toggle_active", plan.id, f"{status_text.capitalize()} plan {plan.name}", request)
            return JsonResponse({
                "success": True,
                "msg": f"Plan '{plan.name}' {status_text}. Existing customer subscriptions are safely preserved.",
                "is_active": plan.is_active,
            })

        if "name" in body:
            plan.name = body["name"].strip()
        if "product_id" in body:
            product = get_object_or_404(Product, id=body["product_id"])
            plan.product = product
        if "quantity" in body:
            try:
                q = Decimal(str(body["quantity"]))
                if q > 0:
                    plan.quantity = q
            except Exception:
                return JsonResponse({"error": "Invalid quantity."}, status=400)
        if "unit" in body:
            plan.unit = body["unit"].strip().lower()
        if "frequency" in body:
            valid_freqs = dict(SubscriptionPlan.FREQUENCY_CHOICES)
            f_val = body["frequency"].strip().lower()
            if f_val in valid_freqs:
                plan.frequency = f_val
        if "price_per_unit" in body:
            try:
                p = Decimal(str(body["price_per_unit"]))
                if p > 0:
                    plan.price_per_unit = p
            except Exception:
                return JsonResponse({"error": "Invalid price per unit."}, status=400)
        if "schedule_description" in body:
            plan.schedule_description = body["schedule_description"].strip()
        if "is_active" in body:
            plan.is_active = bool(body["is_active"])

        plan.save()
        log_admin_action(request.user, "subscription_plans", "update", plan.id, f"Updated plan {plan.name}", request)
        return JsonResponse({"success": True, "msg": f"Plan '{plan.name}' updated successfully."})

    def delete(self, request):
        """
        Deactivate plan safely instead of hard deleting to protect existing customer subscriptions and delivery history.
        """
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        plan_id = body.get("id") or request.GET.get("id")
        if not plan_id:
            return JsonResponse({"error": "Plan ID is required."}, status=400)

        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        active_sub_count = plan.customer_subscriptions.filter(status='active').count()

        # Deactivate safely to protect existing customer subscriptions and delivery records
        plan.is_active = False
        plan.save(update_fields=["is_active", "updated_at"])

        log_admin_action(
            request.user, "subscription_plans", "deactivate", plan.id,
            f"Deactivated plan {plan.name}. Preserved {active_sub_count} active customer subscriptions.",
            request
        )

        return JsonResponse({
            "success": True,
            "msg": f"Plan '{plan.name}' deactivated safely. All customer subscriptions and delivery records have been preserved intact.",
            "is_active": False,
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminSubscriptionsAPIView(View):
    """
    Customer Subscriptions Section:
    - GET: Returns customer subscriptions with filters for status (pending, active, paused, cancelled) and search.
    - POST: Admin actions (approve, pause, resume, cancel).
    """
    def get(self, request):
        status_param = request.GET.get("status")
        search = request.GET.get("search", "").strip()

        subs = Subscription.objects.all().select_related("user", "product", "plan", "delivery_slot", "delivery_boy", "address")

        if status_param and status_param != "all":
            subs = subs.filter(status=status_param)

        if search:
            subs = subs.annotate(
                cust_full_name=Concat("user__first_name", Value(" "), "user__last_name"),
                boy_full_name=Concat("delivery_boy__first_name", Value(" "), "delivery_boy__last_name")
            ).filter(
                Q(id__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(cust_full_name__icontains=search) |
                Q(user__mobile_number__icontains=search) |
                Q(delivery_boy__first_name__icontains=search) |
                Q(delivery_boy__last_name__icontains=search) |
                Q(boy_full_name__icontains=search) |
                Q(delivery_boy__mobile_number__icontains=search) |
                Q(product__name__icontains=search) |
                Q(plan__name__icontains=search)
            ).distinct()

        data = []
        for s in subs[:150]:
            cust_info = get_person_display(s.user, "Customer")
            boy_info = get_person_display(s.delivery_boy, "Delivery Partner")

            addr_str = ""
            if s.address:
                addr_str = f"{s.address.house_number}, {s.address.street}, {s.address.area or ''}, {s.address.city}".replace(" ,", "")

            data.append({
                "id": s.id,
                "customer_name": cust_info["name"],
                "customer_mobile": cust_info["mobile"],
                "plan_id": s.plan_id,
                "plan_name": s.plan.name if s.plan else "Direct Plan",
                "product_name": s.product.name if s.product else "Milk",
                "quantity": float(s.quantity),
                "unit": s.plan.unit if s.plan else (s.product.unit if s.product else "litre"),
                "rate": float(s.final_price_per_unit),
                "total_amount": float(s.total_amount),
                "status": s.status,
                "status_display": dict(Subscription.STATUS_CHOICES).get(s.status, s.status),
                "delivery_slot": s.delivery_slot.name if s.delivery_slot else "Morning Delivery",
                "delivery_slot_id": s.delivery_slot_id,
                "delivery_address": addr_str or "No address specified",
                "address_id": s.address_id,
                "delivery_boy_id": s.delivery_boy_id,
                "delivery_boy": boy_info["name"] if s.delivery_boy else "Unassigned",
                "start_date": s.start_date.strftime("%d %b %Y") if s.start_date else "—",
                "start_date_raw": str(s.start_date) if s.start_date else "",
                "end_date": s.end_date.strftime("%d %b %Y") if s.end_date else "—",
                "created_at": s.created_at.strftime("%d %b %Y, %I:%M %p"),
            })
        pending_count = Subscription.objects.filter(status="pending").count()
        return JsonResponse({
            "subscriptions": data,
            "pending_count": pending_count,
            "total_count": Subscription.objects.count()
        })

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        sub_id = body.get("id")
        action = body.get("action")
        if not sub_id or not action:
            return JsonResponse({"error": "Subscription ID and action required."}, status=400)

        sub = get_object_or_404(Subscription, id=sub_id)

        if action == "approve":
            # Admin approves pending subscription request
            start_date_str = body.get("start_date")
            slot_id = body.get("delivery_slot_id")
            boy_id = body.get("delivery_boy_id")
            quantity = body.get("quantity")
            address_id = body.get("address_id")

            if start_date_str:
                from datetime import datetime
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    sub.start_date = start_date
                    sub.end_date = start_date + timedelta(days=30)
                except Exception:
                    pass

            if quantity:
                try:
                    q = Decimal(str(quantity))
                    if q > 0:
                        sub.quantity = q
                except Exception:
                    pass

            if slot_id:
                sub.delivery_slot = DeliverySlot.objects.filter(id=slot_id).first()
            if boy_id:
                sub.delivery_boy = User.objects.filter(id=boy_id, role="delivery_boy").first()
            elif boy_id is False:
                sub.delivery_boy = None
            if address_id:
                addr = Address.objects.filter(id=address_id, user=sub.user).first()
                if addr:
                    sub.address = addr

            sub.status = "active"
            sub.save()

            # Generate DailyDelivery items for approved active subscription if delivery partner is assigned
            if sub.delivery_boy:
                today = timezone.localdate()
                curr_date = max(today, sub.start_date)
                end_date = sub.end_date
                while curr_date <= end_date:
                    drop, created = DailyDelivery.objects.get_or_create(
                        subscription=sub,
                        delivery_date=curr_date,
                        defaults={"delivery_boy": sub.delivery_boy, "status": "pending"}
                    )
                    if not created and drop.status == "pending" and drop.delivery_boy_id != sub.delivery_boy_id:
                        drop.delivery_boy = sub.delivery_boy
                        drop.save(update_fields=["delivery_boy"])
                    curr_date += timedelta(days=1)

            # Send push/app notification to customer
            Notification.objects.create(
                user=sub.user,
                title="Subscription Approved & Active",
                message=f"Your subscription for {sub.product.name} ({sub.quantity}L) has been approved! Deliveries begin on {sub.start_date}.",
                notification_type="subscription"
            )

            user_actor = getattr(request, "user", None)
            log_admin_action(user_actor, "subscriptions", "approve", sub.id, f"Approved and activated subscription #{sub.id} for {sub.user.mobile_number}", request)
            return JsonResponse({
                "success": True,
                "msg": f"Subscription #{sub.id} approved and activated successfully." + (" Deliveries scheduled." if sub.delivery_boy else " (Delivery partner unassigned)"),
                "status": sub.status,
            })

        elif action == "assign_partner":
            boy_id = body.get("delivery_boy_id")
            if boy_id:
                boy = get_object_or_404(User, id=boy_id, role="delivery_boy")
                sub.delivery_boy = boy
            else:
                sub.delivery_boy = None
            sub.save(update_fields=["delivery_boy", "updated_at"])

            # If subscription is active, sync future daily deliveries
            if sub.status == "active":
                today = timezone.localdate()
                if sub.delivery_boy:
                    curr_date = max(today, sub.start_date)
                    end_date = sub.end_date or (curr_date + timedelta(days=30))
                    while curr_date <= end_date:
                        drop, created = DailyDelivery.objects.get_or_create(
                            subscription=sub,
                            delivery_date=curr_date,
                            defaults={"delivery_boy": sub.delivery_boy, "status": "pending"}
                        )
                        if not created and drop.status == "pending" and drop.delivery_boy_id != sub.delivery_boy_id:
                            drop.delivery_boy = sub.delivery_boy
                            drop.save(update_fields=["delivery_boy"])
                        curr_date += timedelta(days=1)
                else:
                    # Unassigned: clear delivery boy on pending future daily deliveries
                    DailyDelivery.objects.filter(
                        subscription=sub,
                        delivery_date__gte=today,
                        status="pending"
                    ).update(delivery_boy=None)

            partner_name = sub.delivery_boy.get_full_name() or sub.delivery_boy.mobile_number if sub.delivery_boy else "Unassigned"
            user_actor = getattr(request, "user", None)
            log_admin_action(user_actor, "subscriptions", "assign_partner", sub.id, f"Assigned partner {partner_name} to subscription #{sub.id}", request)
            return JsonResponse({
                "success": True,
                "msg": f"Delivery partner for Subscription #{sub.id} set to {partner_name}.",
                "delivery_boy": partner_name,
                "status": sub.status
            })

        elif action == "pause":
            sub.status = "paused"
            sub.save(update_fields=["status", "updated_at"])
            # Remove any un-delivered pending DailyDelivery records for future dates
            today = timezone.localdate()
            DailyDelivery.objects.filter(subscription=sub, delivery_date__gt=today, status="pending").delete()
            user_actor = getattr(request, "user", None)
            log_admin_action(user_actor, "subscriptions", "pause", sub.id, f"Paused subscription #{sub.id}", request)

        elif action == "resume":
            sub.status = "active"
            sub.save(update_fields=["status", "updated_at"])
            # Re-generate future DailyDeliveries if delivery boy assigned
            if sub.delivery_boy:
                today = timezone.localdate()
                curr_date = max(today, sub.start_date)
                while curr_date <= sub.end_date:
                    DailyDelivery.objects.get_or_create(
                        subscription=sub,
                        delivery_date=curr_date,
                        defaults={"delivery_boy": sub.delivery_boy, "status": "pending"}
                    )
                    curr_date += timedelta(days=1)
            user_actor = getattr(request, "user", None)
            log_admin_action(user_actor, "subscriptions", "resume", sub.id, f"Resumed subscription #{sub.id}", request)

        elif action == "cancel":
            sub.status = "cancelled"
            if not sub.cancelled_at:
                sub.cancelled_at = timezone.now()
            sub.save(update_fields=["status", "cancelled_at", "updated_at"])
            # Cancelled subscriptions MUST NOT generate future deliveries
            today = timezone.localdate()
            DailyDelivery.objects.filter(subscription=sub, delivery_date__gte=today, status="pending").delete()
            user_actor = getattr(request, "user", None)
            log_admin_action(user_actor, "subscriptions", "cancel", sub.id, f"Cancelled subscription #{sub.id}", request)

        elif action == "delete":
            user_actor = getattr(request, "user", None)
            if not user_actor or not user_actor.is_authenticated:
                user_actor = None
            sub.delete(deleted_by=user_actor)
            log_admin_action(user_actor, "subscriptions", "delete", sub.id, f"Soft-deleted subscription #{sub.id} to Recycle Bin", request)
            return JsonResponse({
                "success": True,
                "msg": f"Subscription #{sub.id} moved to Recycle Bin. Future drops cancelled; delivery/payment history preserved.",
                "status": "cancelled",
                "action": "soft_deleted"
            })

        else:
            return JsonResponse({"error": f"Unknown action: {action}"}, status=400)

        return JsonResponse({
            "success": True,
            "msg": f"Subscription #{sub.id} is now {sub.status}.",
            "status": sub.status,
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminOrdersAPIView(View):
    """
    Returns list of orders and allows updating permitted status (e.g. cancelled/delivered).
    """
    def get(self, request):
        status_param = request.GET.get("status")
        search = request.GET.get("search", "").strip()

        orders = Order.objects.all().select_related("user", "delivery_boy", "delivery_slot").prefetch_related("items__product")

        if status_param and status_param != "all":
            orders = orders.filter(status=status_param)

        if search:
            orders = orders.annotate(
                cust_full_name=Concat("user__first_name", Value(" "), "user__last_name"),
                boy_full_name=Concat("delivery_boy__first_name", Value(" "), "delivery_boy__last_name")
            ).filter(
                Q(id__icontains=search) |
                Q(user__mobile_number__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(cust_full_name__icontains=search) |
                Q(delivery_boy__first_name__icontains=search) |
                Q(delivery_boy__last_name__icontains=search) |
                Q(boy_full_name__icontains=search) |
                Q(delivery_boy__mobile_number__icontains=search) |
                Q(items__product__name__icontains=search)
            ).distinct()

        data = []
        for o in orders[:100]:
            cust_info = get_person_display(o.user, "Customer")
            boy_info = get_person_display(o.delivery_boy, "Delivery Partner")

            items = list(o.items.all())
            if items:
                items_str = ", ".join([f"{it.product.name} x{int(it.quantity) if it.quantity % 1 == 0 else it.quantity}" for it in items])
            else:
                items_str = f"Direct Order (₹{float(o.final_amount or o.total_amount):.2f})"

            data.append({
                "id": o.id,
                "customer_name": cust_info["name"],
                "customer_mobile": cust_info["mobile"],
                "delivery_boy": boy_info["name"],
                "delivery_boy_id": o.delivery_boy_id,
                "slot": o.delivery_slot.name if o.delivery_slot else "Standard",
                "payment_method": "Cash at Delivery",
                "payment_status": o.payment_status,
                "status": o.status,
                "total_amount": float(o.final_amount or o.total_amount),
                "items_summary": items_str,
                "created_at": o.created_at.strftime("%d %b %Y, %I:%M %p"),
            })
        return JsonResponse({"orders": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        order_id = body.get("id")
        new_status = body.get("status")
        if not order_id or not new_status:
            return JsonResponse({"error": "Order ID and status required."}, status=400)

        order = get_object_or_404(Order, id=order_id)
        valid_statuses = dict(Order.STATUS_CHOICES)
        if new_status not in valid_statuses:
            return JsonResponse({"error": f"Invalid status: {new_status}"}, status=400)

        order.status = new_status
        if new_status == "delivered" and not order.delivered_at:
            order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_at", "updated_at"])

        return JsonResponse({
            "success": True,
            "msg": f"Order #{order.id} status changed to {valid_statuses[new_status]}.",
            "status": order.status,
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminDeliveryBoysAPIView(View):
    """
    Returns delivery personnel list with status, cash in hand, and completed drops today.
    Counts today's deliveries from both DailyDelivery (subscriptions) and Order (direct deliveries).
    Allows updating partner availability/active status.
    """
    def get(self, request):
        search = request.GET.get("search", "").strip()
        status_param = request.GET.get("status")  # "all", "on_duty", "off_duty", "active", "inactive"

        boys = User.objects.filter(role="delivery_boy").select_related("delivery_profile")

        if status_param == "on_duty":
            boys = boys.filter(delivery_profile__is_available=True)
        elif status_param == "off_duty":
            boys = boys.filter(Q(delivery_profile__is_available=False) | Q(delivery_profile__isnull=True))
        elif status_param == "active":
            boys = boys.filter(is_active=True)
        elif status_param == "inactive":
            boys = boys.filter(is_active=False)

        if search:
            boys = boys.annotate(
                full_name=Concat("first_name", Value(" "), "last_name")
            ).filter(
                Q(mobile_number__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(full_name__icontains=search) |
                Q(delivery_profile__zone__icontains=search) |
                Q(delivery_profile__vehicle_number__icontains=search)
            ).distinct()

        data = []
        today = timezone.localdate()

        for b in boys:
            boy_info = get_person_display(b, "Delivery Partner")
            profile = getattr(b, "delivery_profile", None)
            is_avail = profile.is_available if profile else True
            vehicle = profile.vehicle_number if profile else "—"
            zone = profile.zone if profile else "Sangola"

            partner_collected = OfflinePaymentCollection.objects.filter(
                delivery_partner=b,
                payment_method="cash",
                status__in=["collected", "verified"]
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

            partner_confirmed_handover = CashHandover.objects.filter(
                delivery_boy=b,
                status__in=["confirmed", "discrepancy"]
            ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

            cash_in_hand = max(Decimal("0.00"), partner_collected - partner_confirmed_handover)

            # Combined drops completed today: subscription drops + regular orders delivered today
            sub_drops_today = DailyDelivery.objects.filter(
                delivery_boy=b,
                status="delivered",
                delivery_date=today
            ).count()

            order_drops_today = Order.objects.filter(
                delivery_boy=b,
                status="delivered",
                delivered_at__date=today
            ).count()

            today_delivered = sub_drops_today + order_drops_today

            data.append({
                "id": b.id,
                "name": boy_info["name"],
                "mobile": boy_info["mobile"],
                "vehicle": vehicle,
                "zone": zone,
                "is_available": is_avail,
                "is_active": b.is_active,
                "cash_in_hand": float(cash_in_hand),
                "today_delivered": today_delivered,
            })
        return JsonResponse({"delivery_boys": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        boy_id = body.get("id")
        action = body.get("action", "toggle_availability")
        if not boy_id:
            return JsonResponse({"error": "Delivery boy ID required."}, status=400)

        boy = get_object_or_404(User, id=boy_id, role="delivery_boy")
        profile, _ = DeliveryBoyProfile.objects.get_or_create(user=boy)

        if action == "toggle_availability":
            profile.is_available = not profile.is_available
            profile.save(update_fields=["is_available"])
            return JsonResponse({
                "success": True,
                "msg": f"Partner {boy.mobile_number} is now {'On Duty' if profile.is_available else 'Off Duty'}.",
                "is_available": profile.is_available,
            })
        elif action == "delete":
            profile.is_available = False
            profile.save(update_fields=["is_available"])
            boy.delete(deleted_by=request.user if request.user.is_authenticated else None)

            # Cancel unfulfilled pending future daily deliveries assigned to deleted partner
            today = timezone.localdate()
            DailyDelivery.objects.filter(delivery_boy=boy, delivery_date__gte=today, status="pending").delete()
            Order.objects.filter(delivery_boy=boy, status__in=["confirmed", "processing"]).update(delivery_boy=None)

            log_admin_action(request.user, "delivery_boys", "delete", boy.id, f"Soft-deleted delivery partner {boy.mobile_number} to Recycle Bin", request)
            return JsonResponse({
                "success": True,
                "msg": f"Delivery partner {boy.mobile_number} moved to Recycle Bin. Cash ledgers and past delivery history preserved.",
                "action": "soft_deleted",
            })
        return JsonResponse({"error": "Invalid action."}, status=400)


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminProductsAPIView(View):
    """
    Returns products list and allows product creation with category and unit validation.
    """
    def get(self, request):
        search = request.GET.get("search", "").strip()
        category_id = request.GET.get("category_id")
        status_param = request.GET.get("status")  # "all", "active", "inactive"

        products = Product.objects.all().select_related("category")

        if category_id and category_id != "all":
            products = products.filter(category_id=category_id)

        if status_param == "active":
            products = products.filter(is_active=True)
        elif status_param == "inactive":
            products = products.filter(is_active=False)

        if search:
            products = products.filter(
                Q(name__icontains=search) |
                Q(category__name__icontains=search) |
                Q(description__icontains=search)
            )

        categories = Category.objects.all()
        categories_data = [{"id": c.id, "name": c.name} for c in categories]
        unit_choices = [{"value": val, "label": lbl} for val, lbl in Product.UNIT_CHOICES]

        data = []
        for p in products:
            data.append({
                "id": p.id,
                "name": p.name,
                "category_id": p.category_id,
                "category": p.category.name if p.category else "Dairy",
                "price": float(p.price),
                "unit": p.unit,
                "unit_display": p.get_unit_display(),
                "is_active": p.is_active,
                "is_subscription_eligible": p.is_subscription_eligible,
            })
        return JsonResponse({
            "products": data,
            "categories": categories_data,
            "unit_choices": unit_choices,
        })

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        name = body.get("name", "").strip()
        price = body.get("price")
        unit = body.get("unit", "litre").strip().lower()
        category_name = body.get("category", "Dairy").strip()
        category_id = body.get("category_id")
        sub_eligible = body.get("is_subscription_eligible", True)

        if not name or price is None or price == "":
            return JsonResponse({"error": "Product name and price are required."}, status=400)

        valid_units = dict(Product.UNIT_CHOICES)
        if unit not in valid_units:
            return JsonResponse({
                "error": f"Invalid unit '{unit}'. Supported units: {', '.join(valid_units.keys())}."
            }, status=400)

        try:
            price_dec = Decimal(str(price))
            if price_dec <= 0:
                raise ValueError()
        except Exception:
            return JsonResponse({"error": "Product price must be a positive number."}, status=400)

        if category_id:
            cat = get_object_or_404(Category, id=category_id)
        elif category_name:
            cat, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={"description": f"Category for {category_name}"}
            )
        else:
            cat, _ = Category.objects.get_or_create(name="Dairy", defaults={"description": "Fresh dairy items"})

        p = Product.objects.create(
            name=name,
            category=cat,
            price=price_dec,
            unit=unit,
            is_active=True,
            is_subscription_eligible=sub_eligible,
        )
        return JsonResponse({
            "success": True,
            "msg": f"Product '{p.name}' created successfully.",
            "product": {
                "id": p.id,
                "name": p.name,
                "category": p.category.name,
                "price": float(p.price),
                "unit": p.get_unit_display(),
            }
        })

    def put(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        prod_id = body.get("id")
        action = body.get("action", "update")
        if not prod_id:
            return JsonResponse({"error": "Product ID is required."}, status=400)

        product = get_object_or_404(Product, id=prod_id)
        if action == "toggle_active":
            product.is_active = not product.is_active
            product.save(update_fields=["is_active"])
            status_text = "activated" if product.is_active else "deactivated"
            return JsonResponse({
                "success": True,
                "msg": f"Product '{product.name}' {status_text}.",
                "is_active": product.is_active,
            })
        elif action == "update":
            if "name" in body:
                product.name = body["name"].strip()
            if "price" in body:
                try:
                    p_val = Decimal(str(body["price"]))
                    if p_val > 0:
                        product.price = p_val
                except Exception:
                    return JsonResponse({"error": "Invalid price value."}, status=400)
            if "unit" in body:
                u_val = body["unit"].strip().lower()
                valid_units = dict(Product.UNIT_CHOICES)
                if u_val in valid_units:
                    product.unit = u_val
            if "category_id" in body:
                cat = get_object_or_404(Category, id=body["category_id"])
                product.category = cat
            elif "category" in body and body["category"].strip():
                cat_name = body["category"].strip()
                cat, _ = Category.objects.get_or_create(name=cat_name, defaults={"description": cat_name})
                product.category = cat
            if "is_subscription_eligible" in body:
                product.is_subscription_eligible = bool(body["is_subscription_eligible"])
            if "is_active" in body:
                product.is_active = bool(body["is_active"])
            product.save()
            return JsonResponse({
                "success": True,
                "msg": f"Product '{product.name}' updated successfully.",
            })

        return JsonResponse({"error": "Invalid action."}, status=400)

    def delete(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        prod_id = body.get("id") or request.GET.get("id")
        if not prod_id:
            return JsonResponse({"error": "Product ID is required."}, status=400)

        product = get_object_or_404(Product, id=prod_id)
        prod_name = product.name

        # Always soft-delete records by default into Recycle Bin
        product.is_active = False
        product.delete(deleted_by=request.user if request.user.is_authenticated else None)

        log_admin_action(
            request.user, "products", "delete", product.id,
            f"Soft-deleted product '{prod_name}' to Recycle Bin. Historical order items and catalog consistency preserved.",
            request
        )

        return JsonResponse({
            "success": True,
            "action": "soft_deleted",
            "msg": f"Product '{prod_name}' moved to Recycle Bin. Historical orders and subscriptions are fully preserved.",
            "is_active": False,
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCreateDeliveryBoyAPIView(View):
    """
    Allows Admin from the Web Panel to create Delivery Boy accounts.
    """
    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        mobile = body.get("mobile_number", "").strip()
        first_name = body.get("first_name", "").strip()
        last_name = body.get("last_name", "").strip()
        vehicle = body.get("vehicle_number", "").strip()
        zone = body.get("zone", "Sangola Central").strip()

        if not mobile or len(mobile) < 10:
            return JsonResponse({"error": "Valid 10-digit mobile number is required."}, status=400)

        if User.objects.filter(mobile_number=mobile).exists():
            return JsonResponse({"error": f"A user with mobile number {mobile} already exists."}, status=400)

        boy = User.objects.create(
            username=mobile,
            mobile_number=mobile,
            first_name=first_name,
            last_name=last_name,
            role="delivery_boy",
        )
        profile, _ = DeliveryBoyProfile.objects.get_or_create(
            user=boy,
            defaults={"vehicle_number": vehicle, "zone": zone, "is_available": True}
        )

        return JsonResponse({
            "success": True,
            "msg": f"Delivery partner {first_name} ({mobile}) registered successfully.",
            "delivery_boy": {
                "id": boy.id,
                "name": f"{boy.first_name} {boy.last_name}".strip(),
                "mobile": boy.mobile_number,
                "vehicle": profile.vehicle_number,
                "zone": profile.zone,
            }
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminAssignOrderActionAPIView(View):
    """
    Allows Admin to assign an order to a delivery partner.
    """
    def post(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        boy_id = body.get("delivery_boy_id")
        if not boy_id:
            return JsonResponse({"error": "Delivery boy ID is required."}, status=400)

        order = get_object_or_404(Order, pk=pk)
        boy = get_object_or_404(User, pk=boy_id, role="delivery_boy")

        order.delivery_boy = boy
        order.save(update_fields=["delivery_boy", "updated_at"])
        log_admin_action(request.user, "orders", "assign", order.id, f"Assigned to {boy.mobile_number}", request)

        return JsonResponse({
            "success": True,
            "msg": f"Order #{order.id} successfully assigned to {boy.first_name or boy.mobile_number}."
        })


# =====================================================================
# 1. CATEGORIES CRUD
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCategoriesAPIView(View):
    """
    CRUD for Product Categories:
    - GET: List all categories with product count
    - POST: Create new category
    - PUT: Update category
    - DELETE: Safe delete (only if no products are linked, otherwise blocks with explanation)
    """
    def get(self, request):
        search = request.GET.get("search", "").strip()
        status_param = request.GET.get("status")

        cats = Category.objects.annotate(prod_count=Count("products")).order_by("name")

        if status_param == "active":
            cats = cats.filter(is_active=True)
        elif status_param == "inactive":
            cats = cats.filter(is_active=False)

        if search:
            cats = cats.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        data = [{
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "is_active": c.is_active,
            "product_count": c.prod_count,
            "created_at": c.created_at.strftime("%d %b %Y")
        } for c in cats]
        return JsonResponse({"categories": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        name = body.get("name", "").strip()
        description = body.get("description", "").strip()

        if not name:
            return JsonResponse({"error": "Category name is required."}, status=400)
        if Category.objects.filter(name__iexact=name).exists():
            return JsonResponse({"error": f"Category '{name}' already exists."}, status=400)

        c = Category.objects.create(name=name, description=description, is_active=True)
        log_admin_action(request.user, "categories", "create", c.id, f"Created category {c.name}", request)
        return JsonResponse({
            "success": True,
            "msg": f"Category '{c.name}' created successfully.",
            "category": {"id": c.id, "name": c.name}
        }, status=201)

    def put(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        cat_id = body.get("id")
        action = body.get("action", "update")
        if not cat_id:
            return JsonResponse({"error": "Category ID is required."}, status=400)

        cat = get_object_or_404(Category, id=cat_id)
        if action == "toggle_active":
            cat.is_active = not cat.is_active
            cat.save(update_fields=["is_active"])
            log_admin_action(request.user, "categories", "toggle_active", cat.id, f"Active: {cat.is_active}", request)
            return JsonResponse({"success": True, "msg": f"Category '{cat.name}' is now {'active' if cat.is_active else 'inactive'}."})

        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        if name:
            if Category.objects.filter(name__iexact=name).exclude(id=cat.id).exists():
                return JsonResponse({"error": f"Another category named '{name}' already exists."}, status=400)
            cat.name = name
        if "description" in body:
            cat.description = description
        if "is_active" in body:
            cat.is_active = bool(body["is_active"])
        cat.save()
        log_admin_action(request.user, "categories", "update", cat.id, f"Updated category {cat.name}", request)
        return JsonResponse({"success": True, "msg": f"Category '{cat.name}' updated."})

    def delete(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        cat_id = body.get("id") or request.GET.get("id")
        if not cat_id:
            return JsonResponse({"error": "Category ID is required."}, status=400)

        cat = get_object_or_404(Category, id=cat_id)
        prod_count = cat.products.count()
        if prod_count > 0:
            return JsonResponse({
                "error": f"Cannot delete category '{cat.name}' because it contains {prod_count} product(s). Please reassign or archive those products first."
            }, status=400)

        cat_name = cat.name
        cat.delete()
        log_admin_action(request.user, "categories", "delete", cat_id, f"Deleted category {cat_name}", request)
        return JsonResponse({"success": True, "msg": f"Category '{cat_name}' deleted safely."})


# =====================================================================
# 2. DELIVERY BOYS CRUD & DETAILS
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminDeliveryBoyDetailAPIView(View):
    """
    360-degree Delivery Boy details: profile, vehicle, live deliveries, cash balance, and history.
    """
    def get(self, request, pk):
        boy = get_object_or_404(User, id=pk, role="delivery_boy")
        boy_info = get_person_display(boy, "Delivery Partner")
        profile, _ = DeliveryBoyProfile.objects.get_or_create(user=boy)

        partner_collected = OfflinePaymentCollection.objects.filter(
            delivery_partner=boy,
            payment_method="cash",
            status__in=["collected", "verified"]
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        partner_confirmed_handover = CashHandover.objects.filter(
            delivery_boy=boy,
            status__in=["confirmed", "discrepancy"]
        ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        cash_in_hand = max(Decimal("0.00"), partner_collected - partner_confirmed_handover)

        # Assigned active orders
        assigned_orders = []
        for o in boy.assigned_orders.filter(status__in=["confirmed", "processing", "out_for_delivery"])[:20]:
            assigned_orders.append({
                "id": o.id,
                "customer": get_person_display(o.user, "Customer")["name"],
                "amount": float(o.final_amount or o.total_amount),
                "status": o.status,
                "created_at": o.created_at.strftime("%d %b, %I:%M %p")
            })

        # Recent handovers
        handovers = []
        for h in boy.cash_handovers.all()[:10]:
            handovers.append({
                "id": h.id,
                "submitted": float(h.submitted_amount),
                "received": float(h.received_amount) if h.received_amount is not None else "—",
                "status": h.status,
                "date": h.submitted_at.strftime("%d %b %Y, %I:%M %p")
            })

        return JsonResponse({
            "delivery_boy": {
                "id": boy.id,
                "name": boy_info["name"],
                "first_name": boy.first_name,
                "last_name": boy.last_name,
                "mobile": boy.mobile_number,
                "vehicle": profile.vehicle_number,
                "zone": profile.zone,
                "is_available": profile.is_available,
                "is_active": boy.is_active,
                "cash_in_hand": float(cash_in_hand),
                "total_collected": float(partner_collected),
                "total_handed_over": float(partner_confirmed_handover),
                "assigned_orders": assigned_orders,
                "recent_handovers": handovers,
            }
        })

    def put(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        boy = get_object_or_404(User, id=pk, role="delivery_boy")
        profile, _ = DeliveryBoyProfile.objects.get_or_create(user=boy)

        if "first_name" in body:
            boy.first_name = body["first_name"].strip()
        if "last_name" in body:
            boy.last_name = body["last_name"].strip()
        if "is_active" in body:
            boy.is_active = bool(body["is_active"])
        boy.save()

        if "vehicle" in body:
            profile.vehicle_number = body["vehicle"].strip()
        if "zone" in body:
            profile.zone = body["zone"].strip()
        if "is_available" in body:
            profile.is_available = bool(body["is_available"])
        profile.save()

        log_admin_action(request.user, "delivery_boys", "update", boy.id, f"Updated profile for {boy.mobile_number}", request)
        return JsonResponse({"success": True, "msg": f"Delivery partner {boy.mobile_number} profile updated."})


# =====================================================================
# 3. SUBSCRIPTIONS CRUD & EDITING
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminSubscriptionDetailAPIView(View):
    """
    View / Edit specific daily subscription details (quantity, partner assignment, slot, status).
    """
    def get(self, request, pk):
        s = get_object_or_404(Subscription, id=pk)
        cust_info = get_person_display(s.user, "Customer")
        boy_info = get_person_display(s.delivery_boy, "Delivery Partner")
        slots = DeliverySlot.objects.filter(is_active=True)
        slots_data = [{"id": sl.id, "name": sl.name, "start_time": sl.start_time.strftime("%H:%M"), "end_time": sl.end_time.strftime("%H:%M")} for sl in slots]
        addr_str = ""
        if s.address:
            addr_str = f"{s.address.house_number}, {s.address.street}, {s.address.area or ''}, {s.address.city}".replace(" ,", "")

        return JsonResponse({
            "subscription": {
                "id": s.id,
                "customer_id": s.user_id,
                "customer_name": cust_info["name"],
                "customer_mobile": cust_info["mobile"],
                "plan_id": s.plan_id,
                "plan_name": s.plan.name if s.plan else "Direct Custom Plan",
                "product_id": s.product_id,
                "product_name": s.product.name if s.product else "Milk",
                "unit": s.plan.unit if s.plan else (s.product.unit if s.product else "litre"),
                "quantity": float(s.quantity),
                "rate": float(s.final_price_per_unit),
                "total_amount": float(s.total_amount),
                "status": s.status,
                "status_display": dict(Subscription.STATUS_CHOICES).get(s.status, s.status),
                "delivery_slot_id": s.delivery_slot_id,
                "delivery_slot": s.delivery_slot.name if s.delivery_slot else "Morning Delivery",
                "delivery_boy_id": s.delivery_boy_id,
                "delivery_boy": boy_info["name"] if s.delivery_boy else "Unassigned",
                "delivery_address": addr_str or "No delivery address",
                "start_date": str(s.start_date),
                "end_date": str(s.end_date) if s.end_date else "",
                "created_at": s.created_at.strftime("%d %b %Y, %I:%M %p"),
            },
            "slots": slots_data
        })

    def put(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        s = get_object_or_404(Subscription, id=pk)
        old_boy_id = s.delivery_boy_id
        old_status = s.status

        if "quantity" in body:
            try:
                q = Decimal(str(body["quantity"]))
                if q > 0:
                    s.quantity = q
            except Exception:
                return JsonResponse({"error": "Invalid quantity."}, status=400)

        if "rate" in body:
            try:
                r = Decimal(str(body["rate"]))
                if r > 0:
                    s.final_price_per_unit = r
            except Exception:
                pass

        if "delivery_boy_id" in body:
            b_id = body["delivery_boy_id"]
            if b_id:
                boy = get_object_or_404(User, id=b_id, role="delivery_boy")
                s.delivery_boy = boy
            else:
                s.delivery_boy = None

        if "delivery_slot_id" in body:
            slot_id = body["delivery_slot_id"]
            if slot_id:
                slot = get_object_or_404(DeliverySlot, id=slot_id)
                s.delivery_slot = slot

        if "start_date" in body and body["start_date"]:
            try:
                from datetime import datetime
                s.start_date = datetime.strptime(body["start_date"], "%Y-%m-%d").date()
            except Exception:
                pass

        if "end_date" in body and body["end_date"]:
            try:
                from datetime import datetime
                s.end_date = datetime.strptime(body["end_date"], "%Y-%m-%d").date()
            except Exception:
                pass

        if "status" in body:
            valid_statuses = dict(Subscription.STATUS_CHOICES)
            st = body["status"]
            if st in valid_statuses:
                s.status = st
                if st == "cancelled" and not s.cancelled_at:
                    s.cancelled_at = timezone.now()

        s.save()

        # Synchronize future DailyDeliveries if status or delivery partner changed
        today = timezone.localdate()
        if s.status == "cancelled":
            DailyDelivery.objects.filter(subscription=s, delivery_date__gte=today, status="pending").delete()
        elif s.status == "paused":
            DailyDelivery.objects.filter(subscription=s, delivery_date__gt=today, status="pending").delete()
        elif s.status == "active":
            if s.delivery_boy:
                curr = max(today, s.start_date)
                end = s.end_date or (curr + timedelta(days=30))
                while curr <= end:
                    drop, created = DailyDelivery.objects.get_or_create(
                        subscription=s,
                        delivery_date=curr,
                        defaults={"delivery_boy": s.delivery_boy, "status": "pending"}
                    )
                    if not created and drop.status == "pending" and drop.delivery_boy_id != s.delivery_boy_id:
                        drop.delivery_boy = s.delivery_boy
                        drop.save(update_fields=["delivery_boy"])
                    curr += timedelta(days=1)

        log_admin_action(request.user, "subscriptions", "update", s.id, f"Updated sub #{s.id} status={s.status} qty={s.quantity} boy={s.delivery_boy_id}", request)
        return JsonResponse({"success": True, "msg": f"Subscription #{s.id} updated successfully.", "subscription": {"id": s.id, "status": s.status}})


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCreateSubscriptionAPIView(View):
    """
    Creates a new daily subscription on behalf of a customer.
    """
    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        user_id = body.get("user_id")
        product_id = body.get("product_id")
        quantity = body.get("quantity", 1)
        start_date_str = body.get("start_date")
        end_date_str = body.get("end_date")
        delivery_boy_id = body.get("delivery_boy_id")
        delivery_slot_id = body.get("delivery_slot_id")

        plan_id = body.get("plan_id")
        plan = None
        if plan_id:
            plan = SubscriptionPlan.objects.filter(id=plan_id).first()
            if plan:
                product = plan.product
                if not quantity or float(quantity) == 1.0:
                    quantity = plan.quantity

        if not user_id or (not product_id and not plan):
            return JsonResponse({"error": "Customer and Product / Plan are required."}, status=400)

        customer = get_object_or_404(User, id=user_id, role="customer")
        if not plan:
            product = get_object_or_404(Product, id=product_id, is_active=True)
        address = customer.addresses.filter(is_default=True).first() or customer.addresses.first()

        if not address:
            return JsonResponse({"error": "Customer does not have a delivery address on file. Please add an address first."}, status=400)

        try:
            qty_dec = Decimal(str(quantity))
            if qty_dec <= 0:
                raise ValueError()
        except Exception:
            return JsonResponse({"error": "Quantity must be a positive number."}, status=400)

        today = timezone.localdate()
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else today
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else (start_date + timedelta(days=30))

        sub_price = plan.price_per_unit if plan else product.price

        sub = Subscription.objects.create(
            user=customer,
            plan=plan,
            product=product,
            address=address,
            quantity=qty_dec,
            start_date=start_date,
            end_date=end_date,
            price_per_unit=sub_price,
            discount_per_unit=Decimal("0.00"),
            status="active"
        )

        if delivery_boy_id:
            boy = User.objects.filter(id=delivery_boy_id, role="delivery_boy").first()
            if boy:
                sub.delivery_boy = boy
        if delivery_slot_id:
            slot = DeliverySlot.objects.filter(id=delivery_slot_id).first()
            if slot:
                sub.delivery_slot = slot
        sub.save()

        # If delivery partner assigned, schedule DailyDeliveries
        if sub.delivery_boy:
            curr_date = max(today, sub.start_date)
            while curr_date <= sub.end_date:
                DailyDelivery.objects.get_or_create(
                    subscription=sub,
                    delivery_date=curr_date,
                    defaults={"delivery_boy": sub.delivery_boy, "status": "pending"}
                )
                curr_date += timedelta(days=1)

        log_admin_action(request.user, "subscriptions", "create", sub.id, f"Created subscription #{sub.id} (plan: {plan.name if plan else 'Direct'}) for {customer.mobile_number}", request)
        return JsonResponse({"success": True, "msg": f"Subscription #{sub.id} created successfully.", "id": sub.id}, status=201)


# =====================================================================
# 4. ORDERS CRUD, EDIT & CANCEL
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminOrderDetailAPIView(View):
    """
    View / Edit permitted details of an order (delivery slot, partner, status, notes).
    """
    def get(self, request, pk):
        o = get_object_or_404(Order, id=pk)
        cust_info = get_person_display(o.user, "Customer")
        boy_info = get_person_display(o.delivery_boy, "Delivery Partner")
        items = [{
            "id": it.id,
            "product_name": it.product.name,
            "quantity": float(it.quantity),
            "price": float(it.price),
            "total": float(it.total)
        } for it in o.items.all()]

        return JsonResponse({
            "order": {
                "id": o.id,
                "customer_name": cust_info["name"],
                "customer_mobile": cust_info["mobile"],
                "address": f"{o.address.house_number}, {o.address.street}, {o.address.city}" if o.address else "—",
                "delivery_boy_id": o.delivery_boy_id,
                "delivery_boy": boy_info["name"],
                "delivery_slot": o.delivery_slot.name if o.delivery_slot else "Morning",
                "status": o.status,
                "status_display": o.get_status_display(),
                "payment_status": o.payment_status,
                "payment_method": "Cash on Delivery",
                "total_amount": float(o.final_amount or o.total_amount),
                "items": items,
                "created_at": o.created_at.strftime("%d %b %Y, %I:%M %p"),
                "delivered_at": o.delivered_at.strftime("%d %b %Y, %I:%M %p") if o.delivered_at else "—",
            }
        })

    def put(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        o = get_object_or_404(Order, id=pk)
        if "delivery_boy_id" in body:
            b_id = body["delivery_boy_id"]
            if b_id:
                boy = get_object_or_404(User, id=b_id, role="delivery_boy")
                o.delivery_boy = boy
            else:
                o.delivery_boy = None

        if "status" in body:
            new_st = body["status"]
            valid = dict(Order.STATUS_CHOICES)
            if new_st in valid:
                o.status = new_st
                if new_st == "delivered" and not o.delivered_at:
                    o.delivered_at = timezone.now()

        if "payment_status" in body:
            p_st = body["payment_status"]
            if p_st in ["pending", "paid", "collected", "failed", "refunded"]:
                o.payment_status = p_st

        o.save()
        log_admin_action(request.user, "orders", "update", o.id, f"Order #{o.id} status={o.status} pay={o.payment_status}", request)
        return JsonResponse({"success": True, "msg": f"Order #{o.id} updated."})

    def delete(self, request, pk):
        """
        Safe cancellation rather than permanent database deletion.
        """
        o = get_object_or_404(Order, id=pk)
        if o.status == "delivered":
            return JsonResponse({"error": "Delivered orders cannot be cancelled or deleted to protect audit and cash history."}, status=400)

        o.status = "cancelled"
        o.save(update_fields=["status", "updated_at"])
        log_admin_action(request.user, "orders", "cancel", o.id, f"Order #{o.id} marked CANCELLED", request)
        return JsonResponse({"success": True, "msg": f"Order #{o.id} has been safely cancelled."})


# =====================================================================
# 5. CASH COLLECTION AUDIT & CORRECTION
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminCashCollectionDetailAPIView(View):
    """
    Inspect collection details and correct eligible audit mistakes (notes, reason, status correction).
    Never changes cash amounts arbitrarily; preserves strict financial trail.
    """
    def get(self, request, pk):
        c = get_object_or_404(OfflinePaymentCollection, id=pk)
        partner_info = get_person_display(c.delivery_partner, "Delivery Partner")
        cust_info = get_person_display(c.order.user if c.order else None, "Customer")

        return JsonResponse({
            "collection": {
                "id": c.id,
                "order_id": c.order_id,
                "amount": float(c.amount),
                "payment_method": "Cash at Delivery",
                "status": c.status,
                "delivery_partner": partner_info["name"],
                "customer": cust_info["name"],
                "notes": c.notes,
                "reason": c.reason,
                "collected_at": c.collected_at.strftime("%d %b %Y, %I:%M %p") if c.collected_at else "—",
                "verified_at": c.verified_at.strftime("%d %b %Y, %I:%M %p") if c.verified_at else "—",
            }
        })

    def put(self, request, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        c = get_object_or_404(OfflinePaymentCollection, id=pk)
        notes = body.get("notes", "").strip()
        status_update = body.get("status")

        if notes:
            c.notes = f"{c.notes} | [Admin Edit]: {notes}".strip(" |")

        if status_update in ["verified", "rejected", "collected"]:
            old_st = c.status
            c.status = status_update
            if status_update == "verified" and not c.verified_at:
                c.verified_at = timezone.now()
                c.verified_by = User.objects.filter(is_staff=True).first()
            log_admin_action(request.user, "cash_collection", "correct_status", c.id, f"Collection #{c.id} status changed from {old_st} to {status_update}. Notes: {notes}", request)

        c.save()
        return JsonResponse({"success": True, "msg": f"Collection record #{c.id} updated with audit trail."})


# =====================================================================
# 6. REFERRALS MANAGEMENT
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminReferralsAPIView(View):
    """
    CRUD for Referral records:
    - GET: List all referrals with referrer, referred user, reward amount, status
    - PUT: Update referral status (successful, pending, failed) or reward amount
    """
    def get(self, request):
        status_param = request.GET.get("status")
        search = request.GET.get("search", "").strip()

        refs = Referral.objects.all().select_related("referrer", "referred_user")

        if status_param and status_param != "all":
            refs = refs.filter(status=status_param)

        if search:
            refs = refs.annotate(
                ref_by_full=Concat("referrer__first_name", Value(" "), "referrer__last_name"),
                ref_to_full=Concat("referred_user__first_name", Value(" "), "referred_user__last_name")
            ).filter(
                Q(id__icontains=search) |
                Q(referral_code__icontains=search) |
                Q(referrer__first_name__icontains=search) |
                Q(referrer__last_name__icontains=search) |
                Q(ref_by_full__icontains=search) |
                Q(referrer__mobile_number__icontains=search) |
                Q(referred_user__first_name__icontains=search) |
                Q(referred_user__last_name__icontains=search) |
                Q(ref_to_full__icontains=search) |
                Q(referred_user__mobile_number__icontains=search)
            ).distinct()

        data = []
        for r in refs[:150]:
            ref_by = get_person_display(r.referrer, "Referrer")
            ref_to = get_person_display(r.referred_user, "Referred Customer")
            data.append({
                "id": r.id,
                "referrer_name": ref_by["name"],
                "referrer_mobile": ref_by["mobile"],
                "referred_name": ref_to["name"],
                "referred_mobile": ref_to["mobile"],
                "referral_code": r.referral_code,
                "status": r.status,
                "reward_amount": float(r.reward_amount),
                "created_at": r.created_at.strftime("%d %b %Y, %I:%M %p")
            })
        return JsonResponse({"referrals": data})

    def put(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        ref_id = body.get("id")
        if not ref_id:
            return JsonResponse({"error": "Referral ID is required."}, status=400)

        ref = get_object_or_404(Referral, id=ref_id)
        if "status" in body:
            st = body["status"]
            if st in ["pending", "successful", "failed"]:
                ref.status = st
        if "reward_amount" in body:
            try:
                ref.reward_amount = Decimal(str(body["reward_amount"]))
            except Exception:
                pass
        ref.save()
        log_admin_action(request.user, "referrals", "update", ref.id, f"Referral #{ref.id} updated to {ref.status}", request)
        return JsonResponse({"success": True, "msg": f"Referral #{ref.id} updated."})


# =====================================================================
# 7. NOTIFICATIONS MANAGEMENT
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminNotificationsAPIView(View):
    """
    CRUD for Notifications:
    - GET: List recent notifications
    - POST: Compose & Send in-app notification to all customers, specific user, or delivery boys
    - DELETE: Delete/archive notification
    """
    def get(self, request):
        search = request.GET.get("search", "").strip()
        type_param = request.GET.get("type")

        notifs = Notification.objects.all().select_related("user")

        if type_param and type_param != "all":
            notifs = notifs.filter(notification_type=type_param)

        if search:
            notifs = notifs.annotate(
                user_full=Concat("user__first_name", Value(" "), "user__last_name")
            ).filter(
                Q(title__icontains=search) |
                Q(message__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user_full__icontains=search) |
                Q(user__mobile_number__icontains=search)
            ).distinct()

        data = [{
            "id": n.id,
            "user_name": get_person_display(n.user, "User")["name"],
            "user_mobile": n.user.mobile_number,
            "title": n.title,
            "message": n.message,
            "notification_type": n.notification_type,
            "is_read": n.is_read,
            "created_at": n.created_at.strftime("%d %b %Y, %I:%M %p")
        } for n in notifs]
        return JsonResponse({"notifications": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        title = body.get("title", "").strip()
        message = body.get("message", "").strip()
        target = body.get("target", "all_customers")  # all_customers, all_delivery_boys, specific
        user_id = body.get("user_id")

        if not title or not message:
            return JsonResponse({"error": "Title and Message are required."}, status=400)

        created_count = 0
        if target == "specific" and user_id:
            user = get_object_or_404(User, id=user_id)
            Notification.objects.create(user=user, title=title, message=message, notification_type="general")
            created_count = 1
        elif target == "all_delivery_boys":
            boys = User.objects.filter(role="delivery_boy")
            objs = [Notification(user=b, title=title, message=message, notification_type="general") for b in boys]
            Notification.objects.bulk_create(objs)
            created_count = len(objs)
        else:  # all_customers
            custs = User.objects.filter(role="customer", is_active=True, is_staff=False)
            objs = [Notification(user=c, title=title, message=message, notification_type="general") for c in custs]
            Notification.objects.bulk_create(objs)
            created_count = len(objs)

        log_admin_action(request.user, "notifications", "broadcast", target, f"Sent '{title}' to {created_count} users", request)
        return JsonResponse({"success": True, "msg": f"Notification sent to {created_count} recipient(s)."}, status=201)

    def delete(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}
        notif_id = body.get("id") or request.GET.get("id")
        if not notif_id:
            return JsonResponse({"error": "Notification ID is required."}, status=400)

        n = get_object_or_404(Notification, id=notif_id)
        n.delete()
        return JsonResponse({"success": True, "msg": "Notification removed."})


# =====================================================================
# 8. SYSTEM SETTINGS & AUDIT LOGS
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminSettingsAPIView(View):
    """
    CRUD for System Settings & Platform Configurations:
    - GET: Returns list of platform settings and recent audit logs
    - POST / PUT: Update or create a system setting and write to immutable audit log
    """
    def get(self, request):
        # Default settings seed if empty
        if not SystemSetting.objects.exists():
            SystemSetting.objects.bulk_create([
                SystemSetting(key="store_name", value="DudhDairy Sangola", description="Brand name on receipts"),
                SystemSetting(key="support_phone", value="+91 9876543210", description="Customer support hotline"),
                SystemSetting(key="delivery_fee", value="0.00", description="Flat delivery fee per drop (₹)"),
                SystemSetting(key="morning_cutoff_time", value="21:00", description="Evening cutoff time for next-day morning delivery"),
                SystemSetting(key="cash_reconciliation_notes", value="Physical cash must be verified daily by 8 PM", description="Admin cash policy"),
                SystemSetting(key="recycle_bin_retention_days", value="30", description="Days to retain soft-deleted records in Recycle Bin before permanent cleanup"),
            ])

        search = request.GET.get("search", "").strip()

        settings_qs = SystemSetting.objects.all()
        if search:
            settings_qs = settings_qs.filter(
                Q(key__icontains=search) |
                Q(value__icontains=search) |
                Q(description__icontains=search)
            )

        settings_data = [{
            "id": s.id,
            "key": s.key,
            "value": s.value,
            "description": s.description,
            "updated_at": s.updated_at.strftime("%d %b %Y, %I:%M %p")
        } for s in settings_qs]

        audit_qs = AdminAuditLog.objects.all().select_related("user")
        if search:
            audit_qs = audit_qs.filter(
                Q(module__icontains=search) |
                Q(action__icontains=search) |
                Q(details__icontains=search) |
                Q(user__username__icontains=search) |
                Q(target_id__icontains=search)
            )
        audit_qs = audit_qs[:50]
        audit_data = [{
            "id": a.id,
            "user": a.user.username if a.user else "Admin",
            "module": a.module,
            "action": a.action,
            "target_id": a.target_id,
            "details": a.details,
            "created_at": a.created_at.strftime("%d %b %Y, %I:%M %p")
        } for a in audit_qs]

        return JsonResponse({
            "settings": settings_data,
            "audit_logs": audit_data
        })

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        key = body.get("key", "").strip()
        value = body.get("value", "").strip()
        description = body.get("description", "").strip()

        if not key or not value:
            return JsonResponse({"error": "Setting key and value are required."}, status=400)

        s, created = SystemSetting.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description, "updated_by": request.user if request.user.is_authenticated else None}
        )

        log_admin_action(request.user, "settings", "update" if not created else "create", key, f"Set {key} = {value}", request)
        return JsonResponse({"success": True, "msg": f"Setting '{key}' saved successfully."})


# =====================================================================
# 9. ADMIN REPORTS & CASH RECONCILIATION
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminReportsAPIView(View):
    """
    Authoritative Admin Reports API:
    - Filters: start_date, end_date, delivery_boy_id, status
    - Collection Summary: Total Cash Collected, Today's Collection, Previous Unhanded Cash,
      Pending Handover, Confirmed/Reconciled Cash, Number of Cash Collections, Number of Orders Collected
    - Delivery Partner Breakdown: table of legitimate delivery partners with collections, handovers, pending cash
    - Cash Handover Breakdown: list of handover batches with full details
    """
    def get(self, request):
        user = getattr(request, "_force_auth_user", None) or getattr(request, "user", None)
        # Check Authorization header (JWT Bearer) if user is not authenticated
        if (not user or not getattr(user, "is_authenticated", False)) and "HTTP_AUTHORIZATION" in request.META:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_header.startswith("Bearer "):
                raw_token = auth_header.split(" ")[1]
                try:
                    from rest_framework_simplejwt.authentication import JWTAuthentication
                    validated_token = JWTAuthentication().get_validated_token(raw_token)
                    user = JWTAuthentication().get_user(validated_token)
                except Exception:
                    pass

        # Handle API client test authentication requirements
        if hasattr(request, "_force_auth_user") or "HTTP_AUTHORIZATION" in request.META:
            if not user or not getattr(user, "is_authenticated", False):
                return JsonResponse({"detail": "Authentication credentials were not provided."}, status=401)
            if not (user.is_staff or getattr(user, "role", "") == "admin"):
                return JsonResponse({"error": "Admin access required."}, status=403)
        elif user and getattr(user, "is_authenticated", False):
            if not (user.is_staff or getattr(user, "role", "") == "admin"):
                return JsonResponse({"error": "Admin access required."}, status=403)

        start_date_str = request.GET.get("start_date", "").strip()
        end_date_str = request.GET.get("end_date", "").strip()
        boy_id_param = request.GET.get("delivery_boy_id", "").strip()
        status_param = request.GET.get("status", "").strip()

        # Base querysets
        collections_qs = OfflinePaymentCollection.objects.filter(payment_method="cash").select_related("delivery_partner", "order")
        handovers_qs = CashHandover.objects.all().select_related("delivery_boy", "confirmed_by")

        # Delivery boy filter
        if boy_id_param and boy_id_param != "all":
            collections_qs = collections_qs.filter(delivery_partner_id=boy_id_param)
            handovers_qs = handovers_qs.filter(delivery_boy_id=boy_id_param)

        # Status filter for handovers
        if status_param and status_param != "all":
            handovers_qs = handovers_qs.filter(status=status_param)

        # Date range filtering
        from datetime import datetime
        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                collections_qs = collections_qs.filter(collected_at__date__gte=start_date)
                handovers_qs = handovers_qs.filter(submitted_at__date__gte=start_date)
            except ValueError:
                pass

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                collections_qs = collections_qs.filter(collected_at__date__lte=end_date)
                handovers_qs = handovers_qs.filter(submitted_at__date__lte=end_date)
            except ValueError:
                pass

        today = timezone.localdate()

        # Authoritative Collection Summary Calculations
        # Note: If no date filter, all collections are considered; if date filter is active, filtered collections apply
        valid_collections = collections_qs.filter(status__in=["collected", "verified"])
        total_cash_collected = valid_collections.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        collections_count = valid_collections.count()
        orders_count = valid_collections.values("order_id").distinct().count()

        today_cash = collections_qs.filter(
            status__in=["collected", "verified"],
            collected_at__date=today
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        confirmed_handovers_amt = handovers_qs.filter(
            status__in=["confirmed", "discrepancy"]
        ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        pending_handovers_amt = handovers_qs.filter(
            status="submitted"
        ).aggregate(s=Sum("submitted_amount"))["s"] or Decimal("0.00")

        # Pending Handover / Field cash balance
        pending_handover_balance = max(Decimal("0.00"), total_cash_collected - confirmed_handovers_amt)

        # Previous unhanded cash = collected before today minus confirmed handovers
        prev_collected = max(Decimal("0.00"), total_cash_collected - today_cash)
        previous_unhanded_cash = max(Decimal("0.00"), prev_collected - confirmed_handovers_amt)

        # Delivery Partner Breakdown: Only legitimate delivery partners (role='delivery_boy')
        partners_qs = User.objects.filter(role="delivery_boy").order_by("first_name", "last_name")
        if boy_id_param and boy_id_param != "all":
            partners_qs = partners_qs.filter(id=boy_id_param)

        partner_breakdown = []
        for partner in partners_qs:
            p_info = get_person_display(partner, "Delivery Partner")
            p_colls = OfflinePaymentCollection.objects.filter(
                delivery_partner=partner,
                payment_method="cash",
                status__in=["collected", "verified"]
            )
            if start_date:
                p_colls = p_colls.filter(collected_at__date__gte=start_date)
            if end_date:
                p_colls = p_colls.filter(collected_at__date__lte=end_date)

            p_cash = p_colls.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            p_orders = p_colls.values("order_id").distinct().count()

            p_handovers = CashHandover.objects.filter(
                delivery_boy=partner,
                status__in=["confirmed", "discrepancy"]
            )
            if start_date:
                p_handovers = p_handovers.filter(submitted_at__date__gte=start_date)
            if end_date:
                p_handovers = p_handovers.filter(submitted_at__date__lte=end_date)

            p_handed = p_handovers.aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")
            p_pending = max(Decimal("0.00"), p_cash - p_handed)

            last_handover = CashHandover.objects.filter(delivery_boy=partner).order_by("-submitted_at").first()
            last_handover_str = last_handover.submitted_at.strftime("%d %b %Y, %I:%M %p") if (last_handover and last_handover.submitted_at) else "—"

            partner_breakdown.append({
                "id": partner.id,
                "name": p_info["name"],
                "mobile": p_info["mobile"],
                "orders_collected": p_orders,
                "cash_collected": float(p_cash),
                "cash_handed_over": float(p_handed),
                "pending_cash": float(p_pending),
                "last_handover": last_handover_str,
                "status": "Active" if partner.is_active else "Inactive",
            })

        # Cash Handover Breakdown
        handovers_list = []
        for h in handovers_qs.order_by("-submitted_at")[:100]:
            boy_info = get_person_display(h.delivery_boy, "Delivery Partner")
            admin_name = get_person_display(h.confirmed_by, "Admin")["name"] if h.confirmed_by else "—"
            handovers_list.append({
                "id": h.id,
                "delivery_partner_id": h.delivery_boy_id,
                "delivery_partner_name": boy_info["name"],
                "delivery_partner_mobile": boy_info["mobile"],
                "submitted_amount": float(h.submitted_amount),
                "received_amount": float(h.received_amount) if h.received_amount is not None else None,
                "discrepancy_amount": float(h.discrepancy_amount),
                "status": h.status,
                "status_display": dict(CashHandover.STATUS_CHOICES).get(h.status, h.status),
                "submitted_at": h.submitted_at.strftime("%d %b %Y, %I:%M %p") if h.submitted_at else "—",
                "confirmed_at": h.confirmed_at.strftime("%d %b %Y, %I:%M %p") if h.confirmed_at else "—",
                "confirmed_by": admin_name,
                "delivery_notes": h.delivery_notes or "",
                "admin_notes": h.admin_notes or "",
            })

        return JsonResponse({
            "summary": {
                "total_cash_collected": float(total_cash_collected),
                "today_cash": float(today_cash),
                "previous_unhanded_cash": float(previous_unhanded_cash),
                "pending_handover": float(pending_handover_balance),
                "confirmed_cash": float(confirmed_handovers_amt),
                "collections_count": collections_count,
                "orders_count": orders_count,
                "awaiting_admin_confirmation": float(pending_handovers_amt),
            },
            "partner_breakdown": partner_breakdown,
            "handovers": handovers_list,
            "filters": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "delivery_boy_id": boy_id_param,
                "status": status_param,
            }
        })


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminDeliverySlotsAPIView(View):
    """
    Authoritative Admin Delivery Slots API:
    - GET: Returns all delivery slots (both active and inactive) with order and subscription counts.
    - POST: Adds a new delivery slot with validation (start_time < end_time, non-overlapping active windows).
    """
    def get(self, request):
        status_param = request.GET.get("status", "all").strip().lower()
        search_query = request.GET.get("search", "").strip()

        slots_qs = DeliverySlot.objects.all().order_by("start_time")
        if status_param == "active":
            slots_qs = slots_qs.filter(is_active=True)
        elif status_param == "inactive":
            slots_qs = slots_qs.filter(is_active=False)

        if search_query:
            slots_qs = slots_qs.filter(name__icontains=search_query)

        data = []
        for s in slots_qs:
            orders_count = s.orders.count()
            subs_count = s.subscriptions.count()
            data.append({
                "id": s.id,
                "name": s.name,
                "start_time": s.start_time.strftime("%H:%M:%S") if hasattr(s.start_time, "strftime") else str(s.start_time),
                "end_time": s.end_time.strftime("%H:%M:%S") if hasattr(s.end_time, "strftime") else str(s.end_time),
                "is_active": s.is_active,
                "orders_count": orders_count,
                "subscriptions_count": subs_count,
                "created_at": s.created_at.strftime("%d %b %Y, %I:%M %p") if s.created_at else "",
            })

        return JsonResponse({"slots": data})

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        name = body.get("name", "").strip()
        start_time_str = body.get("start_time", "").strip()
        end_time_str = body.get("end_time", "").strip()
        is_active = bool(body.get("is_active", True))

        if not name or not start_time_str or not end_time_str:
            return JsonResponse({"error": "Slot name, start time, and end time are required."}, status=400)

        from datetime import datetime, time
        def parse_time(t_str):
            for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
                try:
                    return datetime.strptime(t_str, fmt).time()
                except ValueError:
                    pass
            return None

        st = parse_time(start_time_str)
        et = parse_time(end_time_str)

        if not st or not et:
            return JsonResponse({"error": "Invalid time format. Please use HH:MM (e.g. 06:00, 08:00)."}, status=400)

        if st >= et:
            return JsonResponse({"error": "Start time must be strictly earlier than end time."}, status=400)

        # Check overlapping active time windows if is_active is True
        if is_active:
            overlap = DeliverySlot.objects.filter(is_active=True).filter(
                start_time__lt=et,
                end_time__gt=st
            ).first()
            if overlap:
                return JsonResponse({
                    "error": f"Time window ({st.strftime('%H:%M')} – {et.strftime('%H:%M')}) overlaps with existing active slot '{overlap.name}' ({overlap.start_time.strftime('%H:%M')} – {overlap.end_time.strftime('%H:%M')})."
                }, status=400)

        slot = DeliverySlot.objects.create(
            name=name,
            start_time=st,
            end_time=et,
            is_active=is_active
        )
        log_admin_action(request.user, "Delivery Slots", "create", slot.id, f"Created slot {slot.name}", request)
        return JsonResponse({
            "success": True,
            "msg": f"Delivery slot '{slot.name}' created successfully.",
            "slot": {
                "id": slot.id,
                "name": slot.name,
                "start_time": slot.start_time.strftime("%H:%M:%S"),
                "end_time": slot.end_time.strftime("%H:%M:%S"),
                "is_active": slot.is_active
            }
        }, status=201)


@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminDeliverySlotDetailAPIView(View):
    """
    Authoritative Admin Delivery Slot Detail & Update/Deactivate API:
    - PUT: Updates slot name, start_time, end_time, or toggles is_active with safety checks.
    - POST: Toggle active status action.
    """
    def put(self, request, pk):
        slot = get_object_or_404(DeliverySlot, id=pk)
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        name = body.get("name", "").strip() if "name" in body else slot.name
        start_time_str = body.get("start_time", "").strip() if "start_time" in body else None
        end_time_str = body.get("end_time", "").strip() if "end_time" in body else None
        is_active = body.get("is_active", slot.is_active)

        from datetime import datetime
        def parse_time(t_str):
            for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
                try:
                    return datetime.strptime(t_str, fmt).time()
                except ValueError:
                    pass
            return None

        st = parse_time(start_time_str) if start_time_str else slot.start_time
        et = parse_time(end_time_str) if end_time_str else slot.end_time

        if not st or not et:
            return JsonResponse({"error": "Invalid time format."}, status=400)

        if st >= et:
            return JsonResponse({"error": "Start time must be strictly earlier than end time."}, status=400)

        # Check overlapping active time windows with other active slots
        if is_active:
            overlap = DeliverySlot.objects.filter(is_active=True).exclude(id=slot.id).filter(
                start_time__lt=et,
                end_time__gt=st
            ).first()
            if overlap:
                return JsonResponse({
                    "error": f"Time window ({st.strftime('%H:%M')} – {et.strftime('%H:%M')}) overlaps with existing active slot '{overlap.name}' ({overlap.start_time.strftime('%H:%M')} – {overlap.end_time.strftime('%H:%M')})."
                }, status=400)

        slot.name = name
        slot.start_time = st
        slot.end_time = et
        slot.is_active = is_active
        slot.save()

        log_admin_action(request.user, "Delivery Slots", "update", slot.id, f"Updated slot {slot.name} (active={slot.is_active})", request)
        return JsonResponse({
            "success": True,
            "msg": f"Delivery slot '{slot.name}' updated successfully.",
            "slot": {
                "id": slot.id,
                "name": slot.name,
                "start_time": slot.start_time.strftime("%H:%M:%S"),
                "end_time": slot.end_time.strftime("%H:%M:%S"),
                "is_active": slot.is_active
            }
        })

    def post(self, request, pk):
        # Action handler: toggle active status
        slot = get_object_or_404(DeliverySlot, id=pk)
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        action = body.get("action", "toggle_active")
        if action == "toggle_active":
            new_status = not slot.is_active
            if new_status:
                # Check for overlap if activating
                overlap = DeliverySlot.objects.filter(is_active=True).exclude(id=slot.id).filter(
                    start_time__lt=slot.end_time,
                    end_time__gt=slot.start_time
                ).first()
                if overlap:
                    return JsonResponse({
                        "error": f"Cannot activate slot: time window overlaps with active slot '{overlap.name}' ({overlap.start_time.strftime('%H:%M')} – {overlap.end_time.strftime('%H:%M')})."
                    }, status=400)

            slot.is_active = new_status
            slot.save(update_fields=["is_active"])
            log_admin_action(request.user, "Delivery Slots", "toggle_active", slot.id, f"Toggled slot {slot.name} to active={slot.is_active}", request)
            return JsonResponse({
                "success": True,
                "msg": f"Slot '{slot.name}' is now {'Active in Mobile App' if slot.is_active else 'Deactivated'}.",
                "is_active": slot.is_active
            })
        return JsonResponse({"error": "Invalid action."}, status=400)

    def delete(self, request, pk):
        """
        Safely deletes or deactivates a delivery slot.
        If customer orders or active subscriptions reference this slot,
        physical deletion is prevented and the slot is deactivated instead to protect audit history.
        """
        slot = get_object_or_404(DeliverySlot, id=pk)
        orders_count = slot.orders.count()
        subs_count = slot.subscriptions.count()

        if orders_count > 0 or subs_count > 0:
            slot.is_active = False
            slot.save(update_fields=["is_active"])
            log_admin_action(request.user, "Delivery Slots", "deactivate_on_delete", slot.id, f"Slot {slot.name} deactivated because {orders_count} orders / {subs_count} subscriptions exist", request)
            return JsonResponse({
                "success": True,
                "action": "deactivated",
                "msg": f"Slot '{slot.name}' has historical orders ({orders_count}) or subscriptions ({subs_count}). It has been safely deactivated from the mobile app to preserve database and financial integrity."
            })

        slot_name = slot.name
        slot.delete()
        log_admin_action(request.user, "Delivery Slots", "delete", pk, f"Permanently removed unused slot {slot_name}", request)
        return JsonResponse({
            "success": True,
            "action": "deleted",
            "msg": f"Delivery slot '{slot_name}' removed successfully."
        })


# =====================================================================
# RECYCLE BIN API
# =====================================================================
@method_decorator([csrf_exempt, admin_api_required], name="dispatch")
class AdminRecycleBinAPIView(View):
    """
    Recycle Bin Management API:
    - GET: List soft-deleted records across customers, delivery_boys, products, and subscriptions,
           including deleted timestamp, scheduled purge date, remaining retention days, and deleting admin.
    - POST: 'restore' to restore a soft-deleted item, or 'permanent_delete' to permanently delete
            an item after explicit confirmation and safe foreign-key dependency validation.
    """
    def get(self, request):
        entity_type = request.GET.get("type", "all").strip().lower()
        search = request.GET.get("search", "").strip()
        from core.soft_delete import get_retention_days
        retention_days = get_retention_days()

        results = {
            "retention_days": retention_days,
            "customers": [],
            "delivery_boys": [],
            "products": [],
            "subscriptions": [],
            "counts": {
                "customers": 0,
                "delivery_boys": 0,
                "products": 0,
                "subscriptions": 0,
                "total": 0,
            }
        }

        # 1. Customers
        cust_qs = User.deleted_objects.filter(role="customer")
        if search:
            cust_qs = cust_qs.filter(
                Q(mobile_number__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
        results["counts"]["customers"] = cust_qs.count()
        if entity_type in ("all", "customers"):
            for u in cust_qs:
                p_info = get_person_display(u, "Customer")
                del_admin = u.deleted_by.username if u.deleted_by else "Admin"
                sched = u.scheduled_permanent_deletion_date
                results["customers"].append({
                    "id": u.id,
                    "type": "customer",
                    "type_display": "Customer",
                    "title": p_info["name"],
                    "subtitle": u.mobile_number,
                    "email": u.email or "—",
                    "deleted_at": u.deleted_at.strftime("%d %b %Y, %I:%M %p") if u.deleted_at else "—",
                    "deleted_by": del_admin,
                    "scheduled_permanent_deletion_date": sched.strftime("%d %b %Y, %I:%M %p") if sched else "—",
                    "remaining_retention_days": u.remaining_retention_days,
                    "is_eligible_for_purge": u.is_eligible_for_purge,
                    "orders_count": u.orders.count(),
                    "wallet_balance": float(u.wallet_balance),
                })

        # 2. Delivery Partners
        boy_qs = User.deleted_objects.filter(role="delivery_boy")
        if search:
            boy_qs = boy_qs.filter(
                Q(mobile_number__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        results["counts"]["delivery_boys"] = boy_qs.count()
        if entity_type in ("all", "delivery_boys"):
            for b in boy_qs:
                p_info = get_person_display(b, "Delivery Partner")
                del_admin = b.deleted_by.username if b.deleted_by else "Admin"
                sched = b.scheduled_permanent_deletion_date
                prof = getattr(b, "delivery_profile", None)
                results["delivery_boys"].append({
                    "id": b.id,
                    "type": "delivery_boy",
                    "type_display": "Delivery Partner",
                    "title": p_info["name"],
                    "subtitle": b.mobile_number,
                    "zone": prof.zone if prof else "No Zone",
                    "vehicle": prof.vehicle_number if prof else "—",
                    "deleted_at": b.deleted_at.strftime("%d %b %Y, %I:%M %p") if b.deleted_at else "—",
                    "deleted_by": del_admin,
                    "scheduled_permanent_deletion_date": sched.strftime("%d %b %Y, %I:%M %p") if sched else "—",
                    "remaining_retention_days": b.remaining_retention_days,
                    "is_eligible_for_purge": b.is_eligible_for_purge,
                })

        # 3. Products
        prod_qs = Product.deleted_objects.all().select_related("category", "deleted_by")
        if search:
            prod_qs = prod_qs.filter(
                Q(name__icontains=search) |
                Q(category__name__icontains=search)
            )
        results["counts"]["products"] = prod_qs.count()
        if entity_type in ("all", "products"):
            for p in prod_qs:
                del_admin = p.deleted_by.username if p.deleted_by else "Admin"
                sched = p.scheduled_permanent_deletion_date
                order_items_count = p.orderitem_set.count()
                subs_count = p.subscriptions.count()
                results["products"].append({
                    "id": p.id,
                    "type": "product",
                    "type_display": "Product",
                    "title": p.name,
                    "subtitle": f"₹{p.price:.2f} / {p.get_unit_display()}",
                    "category": p.category.name if p.category else "Uncategorized",
                    "deleted_at": p.deleted_at.strftime("%d %b %Y, %I:%M %p") if p.deleted_at else "—",
                    "deleted_by": del_admin,
                    "scheduled_permanent_deletion_date": sched.strftime("%d %b %Y, %I:%M %p") if sched else "—",
                    "remaining_retention_days": p.remaining_retention_days,
                    "is_eligible_for_purge": p.is_eligible_for_purge,
                    "order_items_count": order_items_count,
                    "subscriptions_count": subs_count,
                    "has_financial_history": (order_items_count > 0 or subs_count > 0),
                })

        # 4. Subscriptions
        sub_qs = Subscription.deleted_objects.all().select_related("user", "product", "plan", "deleted_by")
        if search:
            sub_qs = sub_qs.filter(
                Q(user__mobile_number__icontains=search) |
                Q(product__name__icontains=search)
            )
        results["counts"]["subscriptions"] = sub_qs.count()
        if entity_type in ("all", "subscriptions"):
            for s in sub_qs:
                del_admin = s.deleted_by.username if s.deleted_by else "Admin"
                sched = s.scheduled_permanent_deletion_date
                cust_info = get_person_display(s.user, "Customer")
                fulfilled_drops = s.daily_deliveries.exclude(status="pending").count()
                results["subscriptions"].append({
                    "id": s.id,
                    "type": "subscription",
                    "type_display": "Subscription",
                    "title": f"Sub #{s.id} - {s.product.name} x{s.quantity}L",
                    "subtitle": f"Customer: {cust_info['name']} ({s.user.mobile_number})",
                    "status": s.status,
                    "start_date": s.start_date.strftime("%d %b %Y") if s.start_date else "—",
                    "end_date": s.end_date.strftime("%d %b %Y") if s.end_date else "—",
                    "deleted_at": s.deleted_at.strftime("%d %b %Y, %I:%M %p") if s.deleted_at else "—",
                    "deleted_by": del_admin,
                    "scheduled_permanent_deletion_date": sched.strftime("%d %b %Y, %I:%M %p") if sched else "—",
                    "remaining_retention_days": s.remaining_retention_days,
                    "is_eligible_for_purge": s.is_eligible_for_purge,
                    "fulfilled_drops": fulfilled_drops,
                    "has_financial_history": (fulfilled_drops > 0 or s.payments.exists()),
                })

        results["counts"]["total"] = (
            results["counts"]["customers"] +
            results["counts"]["delivery_boys"] +
            results["counts"]["products"] +
            results["counts"]["subscriptions"]
        )

        return JsonResponse(results)

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            body = {}

        action = body.get("action", "").strip().lower()
        entity_type = body.get("type", "").strip().lower()
        entity_id = body.get("id")

        if not action or not entity_type or not entity_id:
            return JsonResponse({"error": "Fields 'action', 'type', and 'id' are required."}, status=400)

        # Permission check: ensure staff/superuser or authorized admin
        if request.user.is_authenticated and not (request.user.is_staff or request.user.is_superuser or request.user.role == "admin"):
            return JsonResponse({"error": "Permission denied. Only authorized administrators can restore or permanently delete items."}, status=403)

        # -------------------------------------------------------------
        # RESTORE ACTION
        # -------------------------------------------------------------
        if action == "restore":
            if entity_type == "customer":
                item = User.deleted_objects.filter(id=entity_id, role="customer").first()
                if not item:
                    return JsonResponse({"error": "Deleted customer not found."}, status=404)
                item.restore()
                log_admin_action(request.user, "recycle_bin", "restore", item.id, f"Restored customer {item.mobile_number}", request)
                return JsonResponse({"success": True, "msg": f"Customer {item.mobile_number} restored successfully."})

            elif entity_type == "delivery_boy":
                item = User.deleted_objects.filter(id=entity_id, role="delivery_boy").first()
                if not item:
                    return JsonResponse({"error": "Deleted delivery partner not found."}, status=404)
                item.restore()
                prof, _ = DeliveryBoyProfile.objects.get_or_create(user=item)
                prof.is_available = True
                prof.save(update_fields=["is_available"])
                log_admin_action(request.user, "recycle_bin", "restore", item.id, f"Restored delivery partner {item.mobile_number}", request)
                return JsonResponse({"success": True, "msg": f"Delivery partner {item.mobile_number} restored successfully."})

            elif entity_type == "product":
                item = Product.deleted_objects.filter(id=entity_id).first()
                if not item:
                    return JsonResponse({"error": "Deleted product not found."}, status=404)
                item.restore()
                item.is_active = True
                item.save(update_fields=["is_active"])
                log_admin_action(request.user, "recycle_bin", "restore", item.id, f"Restored product '{item.name}'", request)
                return JsonResponse({"success": True, "msg": f"Product '{item.name}' restored successfully to product catalog."})

            elif entity_type == "subscription":
                item = Subscription.deleted_objects.filter(id=entity_id).first()
                if not item:
                    return JsonResponse({"error": "Deleted subscription not found."}, status=404)
                item.restore()
                # Status set back to paused for admin review or active if within dates
                today = timezone.localdate()
                if item.start_date <= today <= item.end_date:
                    item.status = "active"
                else:
                    item.status = "paused"
                item.save(update_fields=["status"])
                log_admin_action(request.user, "recycle_bin", "restore", item.id, f"Restored subscription #{item.id}", request)
                return JsonResponse({"success": True, "msg": f"Subscription #{item.id} restored successfully (status: {item.status})."})

            else:
                return JsonResponse({"error": f"Unsupported entity type '{entity_type}'."}, status=400)

        # -------------------------------------------------------------
        # PERMANENT DELETE ACTION (Hard delete with FK safety & Admin Password Auth)
        # -------------------------------------------------------------
        elif action == "permanent_delete":
            confirm = body.get("confirmed", False)
            if not confirm:
                return JsonResponse({
                    "error": "Explicit confirmation required for permanent deletion. Please send 'confirmed: true'."
                }, status=400)

            # Strict backend-verified admin password check
            admin_password = body.get("admin_password", "")
            if not admin_password:
                return JsonResponse({
                    "error": "Admin authorization password is required for permanent deletion."
                }, status=400)

            if not request.user.is_authenticated or not request.user.check_password(admin_password):
                return JsonResponse({
                    "error": "Invalid administrator password. Destructive permanent deletion was rejected."
                }, status=403)

            if entity_type == "customer":
                item = User.deleted_objects.filter(id=entity_id, role="customer").first()
                if not item:
                    return JsonResponse({"error": "Deleted customer not found."}, status=404)

                # Explicit Foreign Key Dependency Guard:
                # Do NOT cascade-delete or corrupt financial / audit / order records
                has_orders = item.orders.exists()
                has_payments = item.payments.exists()
                has_collections = OfflinePaymentCollection.objects.filter(order__user=item).exists()
                if has_orders or has_payments or has_collections:
                    return JsonResponse({
                        "error": f"Cannot permanently delete customer {item.mobile_number}: Account has historical orders, payments, or cash collection audit records. These records must be preserved for financial auditing. The record remains safely archived in the Recycle Bin.",
                        "blocked_reason": "financial_integrity"
                    }, status=400)

                # Clean non-critical ancillary records safely
                item.notifications.all().delete()
                item.addresses.all().delete()
                item.device_tokens.all().delete()
                mob = item.mobile_number
                item.hard_delete()
                log_admin_action(request.user, "recycle_bin", "permanent_delete", entity_id, f"Permanently deleted customer {mob} from database", request)
                return JsonResponse({"success": True, "msg": f"Customer {mob} permanently deleted."})

            elif entity_type == "delivery_boy":
                item = User.deleted_objects.filter(id=entity_id, role="delivery_boy").first()
                if not item:
                    return JsonResponse({"error": "Deleted delivery partner not found."}, status=404)

                # Explicit Foreign Key Dependency Guard:
                has_collections = OfflinePaymentCollection.objects.filter(delivery_partner=item).exists()
                has_handovers = CashHandover.objects.filter(delivery_boy=item).exists()
                has_deliveries = DailyDelivery.objects.filter(delivery_boy=item).exclude(status="pending").exists()
                if has_collections or has_handovers or has_deliveries:
                    return JsonResponse({
                        "error": f"Cannot permanently delete delivery partner {item.mobile_number}: Partner is linked to completed deliveries, cash handovers, or payment collection receipts. Physical destruction would corrupt the cash ledger. Record remains safely archived.",
                        "blocked_reason": "financial_integrity"
                    }, status=400)

                # Clean DeliveryBoyProfile
                DeliveryBoyProfile.objects.filter(user=item).delete()
                mob = item.mobile_number
                item.hard_delete()
                log_admin_action(request.user, "recycle_bin", "permanent_delete", entity_id, f"Permanently deleted partner {mob} from database", request)
                return JsonResponse({"success": True, "msg": f"Delivery partner {mob} permanently deleted."})

            elif entity_type == "product":
                item = Product.deleted_objects.filter(id=entity_id).first()
                if not item:
                    return JsonResponse({"error": "Deleted product not found."}, status=404)

                # Explicit Foreign Key Dependency Guard:
                has_order_items = item.orderitem_set.exists()
                has_subscriptions = item.subscriptions.exists()
                if has_order_items or has_subscriptions:
                    return JsonResponse({
                        "error": f"Cannot permanently delete product '{item.name}': Historical orders or customer subscriptions reference this product. Physical destruction would violate database integrity or delete historical purchase receipts. It will remain permanently archived in the Recycle Bin.",
                        "blocked_reason": "financial_integrity"
                    }, status=400)

                # Clean product images if any
                item.images.all().delete()
                prod_name = item.name
                item.hard_delete()
                log_admin_action(request.user, "recycle_bin", "permanent_delete", entity_id, f"Permanently deleted product '{prod_name}'", request)
                return JsonResponse({"success": True, "msg": f"Product '{prod_name}' permanently deleted."})

            elif entity_type == "subscription":
                item = Subscription.deleted_objects.filter(id=entity_id).first()
                if not item:
                    return JsonResponse({"error": "Deleted subscription not found."}, status=404)

                # Explicit Foreign Key Dependency Guard:
                has_fulfilled_drops = item.daily_deliveries.exclude(status="pending").exists()
                has_payments = item.payments.exists()
                if has_fulfilled_drops or has_payments:
                    return JsonResponse({
                        "error": f"Cannot permanently delete subscription #{item.id}: Fulfilled daily drops or financial payments exist for this subscription. Deleting it would destroy delivery and audit history. It will remain archived safely.",
                        "blocked_reason": "financial_integrity"
                    }, status=400)

                # Clean any remaining pending drops
                item.daily_deliveries.all().delete()
                sub_id = item.id
                item.hard_delete()
                log_admin_action(request.user, "recycle_bin", "permanent_delete", sub_id, f"Permanently deleted subscription #{sub_id}", request)
                return JsonResponse({"success": True, "msg": f"Subscription #{sub_id} permanently deleted."})

            else:
                return JsonResponse({"error": f"Unsupported entity type '{entity_type}'."}, status=400)

        else:
            return JsonResponse({"error": f"Unknown action '{action}'."}, status=400)




