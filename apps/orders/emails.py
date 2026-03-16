# apps/orders/emails.py — 100% Professional Industry Standard

import logging
import threading
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def get_estimated_delivery():
    """3-5 business days — weekends skip"""
    today     = timezone.now().date()
    min_date  = today
    max_date  = today
    min_count = 0
    max_count = 0
    days      = 0

    while min_count < 3 or max_count < 5:
        days += 1
        day = today + timedelta(days=days)
        if day.weekday() < 5:
            if min_count < 3:
                min_count += 1
                min_date = day
            if max_count < 5:
                max_count += 1
                max_date = day

    return min_date.strftime('%b %d'), max_date.strftime('%b %d, %Y')


def build_order_email_html(order, payment_method, payment_status):
    """Build 100% professional HTML email"""

    frontend_url     = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    est_min, est_max = get_estimated_delivery()

    if payment_status == 'paid':
        badge_color = '#16a34a'
        badge_text  = '✅ Paid'
    else:
        badge_color = '#d97706'
        badge_text  = '⏳ Pending'

    method_label = {'esewa': 'eSewa', 'cod': 'Cash on Delivery'}.get(payment_method, payment_method.title())

    items_html = ''
    for item in order.items.select_related('product').all():
        product = item.product
        img_url = f"http://127.0.0.1:8000{product.image}" if product.image else ''
        img_tag = (
            f'<img src="{img_url}" width="56" height="56" style="border-radius:8px;object-fit:cover;display:block;" />'
            if img_url else
            '<div style="width:56px;height:56px;background:#f3e8ff;border-radius:8px;text-align:center;line-height:56px;font-size:24px;">🧴</div>'
        )
        items_html += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #f3f4f6;">
            <table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
              <td width="68" style="vertical-align:middle;padding-right:12px;">{img_tag}</td>
              <td style="vertical-align:middle;">
                <p style="margin:0 0 2px;font-size:14px;font-weight:600;color:#111827;">{product.name}</p>
                <p style="margin:0;font-size:12px;color:#6b7280;">{product.brand} &nbsp;·&nbsp; Qty: {item.quantity}</p>
              </td>
              <td style="text-align:right;vertical-align:middle;white-space:nowrap;">
                <p style="margin:0;font-size:14px;font-weight:700;color:#7c3aed;">Rs. {item.total_price}</p>
              </td>
            </tr></table>
          </td>
        </tr>"""

    address_line2_str = f", {order.address_line2}" if getattr(order, 'address_line2', '') else ''
    state_str         = f", {order.state}"         if getattr(order, 'state', '')        else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Order Confirmed — ✨ SkinCare</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f9fafb;padding:32px 16px;">
<tr><td align="center">
<table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;">

  <tr><td>
    <div style="background:linear-gradient(135deg,#7c3aed,#ec4899);border-radius:16px 16px 0 0;padding:32px;text-align:center;">
      <p style="margin:0 0 4px;font-size:32px;">✨</p>
      <h1 style="margin:0;font-size:24px;font-weight:800;color:#fff;">SkinCare</h1>
      <p style="margin:8px 0 0;font-size:14px;color:rgba(255,255,255,0.85);">Order Confirmation</p>
    </div>
  </td></tr>

  <tr><td style="background:#fff;padding:32px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
    <h2 style="margin:0 0 8px;font-size:20px;font-weight:700;color:#111827;">Thank you for your order! 🎉</h2>
    <p style="margin:0 0 24px;font-size:14px;color:#6b7280;line-height:1.6;">
      Hi <strong>{order.user.get_full_name() or order.user.email}</strong>, your order has been received and is being processed.
    </p>

    <div style="background:#f5f3ff;border-radius:12px;padding:16px 20px;margin-bottom:24px;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
        <td style="padding:4px 0;">
          <span style="font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;">Order</span><br/>
          <span style="font-size:18px;font-weight:800;color:#7c3aed;">#{order.id}</span>
        </td>
        <td style="text-align:center;padding:4px 0;">
          <span style="font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;">Date</span><br/>
          <span style="font-size:14px;font-weight:600;color:#111827;">{order.created_at.strftime('%b %d, %Y')}</span>
        </td>
        <td style="text-align:right;padding:4px 0;">
          <span style="font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;">Status</span><br/>
          <span style="font-size:14px;font-weight:700;color:#16a34a;">⚙️ Processing</span>
        </td>
      </tr></table>
    </div>

    <p style="margin:0 0 12px;font-size:12px;font-weight:700;color:#374151;text-transform:uppercase;">🛍️ Order Items</p>
    <table cellpadding="0" cellspacing="0" border="0" width="100%">{items_html}</table>

    <div style="margin-top:16px;padding-top:16px;border-top:2px solid #f3f4f6;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td style="padding:3px 0;font-size:13px;color:#6b7280;">Subtotal</td>
          <td style="text-align:right;font-size:13px;color:#374151;">Rs. {order.subtotal}</td>
        </tr>
        <tr>
          <td style="padding:3px 0;font-size:13px;color:#6b7280;">Shipping</td>
          <td style="text-align:right;font-size:13px;color:#16a34a;font-weight:600;">Free ✨</td>
        </tr>
        <tr>
          <td style="padding:12px 0 0;font-size:16px;font-weight:800;color:#111827;border-top:1px solid #e5e7eb;">Total</td>
          <td style="padding:12px 0 0;text-align:right;font-size:20px;font-weight:800;color:#7c3aed;border-top:1px solid #e5e7eb;">Rs. {order.total_amount}</td>
        </tr>
      </table>
    </div>

    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:24px;">
      <tr>
        <td width="49%" style="vertical-align:top;">
          <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;">💳 Payment</p>
            <p style="margin:0 0 8px;font-size:14px;font-weight:600;color:#111827;">{method_label}</p>
            <span style="background:{badge_color};color:#fff;font-size:11px;font-weight:700;padding:3px 12px;border-radius:20px;display:inline-block;">{badge_text}</span>
          </div>
        </td>
        <td width="2%"></td>
        <td width="49%" style="vertical-align:top;">
          <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
            <p style="margin:0 0 8px;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;">📅 Est. Delivery</p>
            <p style="margin:0 0 4px;font-size:14px;font-weight:600;color:#111827;">{est_min} – {est_max}</p>
            <p style="margin:0;font-size:12px;color:#6b7280;">3–5 business days</p>
          </div>
        </td>
      </tr>
    </table>

    <div style="margin-top:20px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
      <p style="margin:0 0 10px;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;">📍 Delivery Address</p>
      <p style="margin:0;font-size:14px;color:#374151;line-height:1.8;">
        <strong>{order.full_name}</strong><br/>
        {order.address_line1}{address_line2_str}<br/>
        {order.city}{state_str}<br/>
        📞 {order.phone}
      </p>
    </div>

    <div style="text-align:center;margin-top:28px;">
      <a href="{frontend_url}/orders"
        style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#ec4899);color:#fff;font-size:14px;font-weight:700;padding:14px 36px;border-radius:12px;text-decoration:none;">
        Track My Order →
      </a>
    </div>
  </td></tr>

  <tr><td>
    <div style="background:#f3f4f6;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:none;padding:20px 32px;text-align:center;">
      <p style="margin:0 0 6px;font-size:13px;color:#6b7280;">
        Questions? <a href="mailto:support@skincare.com" style="color:#7c3aed;text-decoration:none;font-weight:600;">support@skincare.com</a>
      </p>
      <p style="margin:0;font-size:12px;color:#9ca3af;">© 2026 ✨ SkinCare · Kathmandu, Nepal</p>
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def send_order_confirmation_email(order, payment_method='cod', payment_status='pending'):
    """
    100% Professional — Non-blocking async email via background thread.
    Triggered after: COD order placed / eSewa payment verified.
    """
    order_id     = order.id
    user_email   = order.user.email
    user_name    = order.user.get_full_name() or order.user.email
    total        = order.total_amount
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    method_label = {'esewa': 'eSewa', 'cod': 'Cash on Delivery'}.get(payment_method, payment_method.title())

    def _send():
        try:
            print(f"📧 Sending email to {user_email} for order #{order_id}...")
            print(f"   HOST: {settings.EMAIL_HOST}")
            print(f"   PORT: {settings.EMAIL_PORT}")
            print(f"   USER: {settings.EMAIL_HOST_USER}")

            html_content = build_order_email_html(order, payment_method, payment_status)
            subject      = f"Order Confirmed #{order_id} — ✨ SkinCare"
            text_content = f"""Hi {user_name},

Your order #{order_id} has been confirmed!

Total: Rs. {total}
Payment: {method_label} — {payment_status.title()}
Estimated Delivery: 3–5 business days

Track your order: {frontend_url}/orders

Thank you for shopping with ✨ SkinCare!
Need help? support@skincare.com""".strip()

            msg = EmailMultiAlternatives(
                subject    = subject,
                body       = text_content,
                from_email = settings.DEFAULT_FROM_EMAIL,
                to         = [user_email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)

            print(f"✅ Email sent successfully to {user_email} for order #{order_id}!")
            logger.info("✅ Order confirmation email sent → %s (Order #%s)", user_email, order_id)

        except Exception as e:
            print(f"❌ Email failed for order #{order_id}: {e}")
            logger.error("❌ Email failed for order #%s: %s", order_id, str(e))

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()