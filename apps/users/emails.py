# apps/users/emails.py

import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


def send_otp_email(user, otp_code) -> bool:
    """Send OTP verification email"""
    try:
        subject = "Your verification code — Skincare App"

        text_content = f"""
Hi {user.get_short_name()},

Your verification code is: {otp_code}

This code expires in 10 minutes.

If you did not register, please ignore this email.

— Skincare App Team
        """.strip()

        html_content = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="500" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.07);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#7c3aed,#ec4899);padding:40px;text-align:center;">
              <div style="font-size:40px;margin-bottom:10px;">✨</div>
              <h1 style="color:#ffffff;margin:0;font-size:24px;font-weight:bold;">
                Verify Your Email
              </h1>
              <p style="color:#e9d5ff;margin:8px 0 0;font-size:14px;">SkinCare App</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px;">
              <p style="color:#374151;font-size:16px;margin:0 0 8px;">
                Hi <strong>{user.get_short_name()}</strong>,
              </p>
              <p style="color:#6b7280;font-size:15px;margin:0 0 30px;">
                Enter this code to verify your email address:
              </p>

              <!-- OTP Box -->
              <div style="text-align:center;margin:0 0 30px;">
                <div style="display:inline-block;background:#f5f3ff;border:2px dashed #7c3aed;
                            border-radius:16px;padding:24px 48px;">
                  <p style="margin:0 0 4px;color:#7c3aed;font-size:13px;font-weight:bold;
                             letter-spacing:2px;text-transform:uppercase;">
                    Verification Code
                  </p>
                  <p style="margin:0;font-size:48px;font-weight:bold;color:#7c3aed;
                             letter-spacing:12px;">
                    {otp_code}
                  </p>
                </div>
              </div>

              <!-- Expiry -->
              <div style="background:#fef3c7;border-radius:10px;padding:14px;margin-bottom:24px;text-align:center;">
                <p style="color:#92400e;font-size:13px;margin:0;">
                  ⏰ This code expires in <strong>10 minutes</strong>
                </p>
              </div>

              <p style="color:#9ca3af;font-size:13px;margin:0;text-align:center;">
                Do not share this code with anyone.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f9fafb;padding:24px;text-align:center;border-top:1px solid #f3f4f6;">
              <p style="color:#9ca3af;font-size:12px;margin:0;">
                If you did not register, please ignore this email.
              </p>
              <p style="color:#9ca3af;font-size:12px;margin:8px 0 0;">— Skincare App Team</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        logger.info("OTP email sent to %s", user.email)
        return True

    except Exception as e:
        logger.error("Failed to send OTP email to %s: %s", user.email, str(e))
        return False


def send_welcome_email(user) -> bool:
    """Send welcome email after verification"""
    try:
        subject = "Welcome to Skincare App! 🎉"

        html_content = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="500" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;overflow:hidden;">
          <tr>
            <td style="background:linear-gradient(135deg,#059669,#7c3aed);padding:40px;text-align:center;">
              <div style="font-size:50px;margin-bottom:10px;">🎉</div>
              <h1 style="color:#ffffff;margin:0;font-size:24px;">Welcome to SkinCare!</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:40px;text-align:center;">
              <p style="color:#374151;font-size:16px;">
                Hi <strong>{user.get_short_name()}</strong>, your account is now active!
              </p>
              <a href="{settings.FRONTEND_URL}/login"
                 style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#ec4899);
                        color:#ffffff;text-decoration:none;font-size:16px;font-weight:bold;
                        padding:16px 40px;border-radius:12px;margin-top:16px;">
                Start Shopping →
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Hi {user.get_short_name()}, welcome to Skincare App!",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        logger.info("Welcome email sent to %s", user.email)
        return True

    except Exception as e:
        logger.error("Failed to send welcome email to %s: %s", user.email, str(e))
        return False 
      
  # apps/users/emails.py मा यो function थप्नुस् (file को अन्तमा)

def send_password_changed_email(user, ip_address='Unknown', device='Unknown') -> bool:
    """Send security alert email after password change"""
    from django.utils import timezone
    changed_at = timezone.now().strftime('%B %d, %Y at %I:%M %p UTC')

    try:
        subject = "⚠️ Your password was changed — Skincare App"

        text_content = f"""
Hi {user.get_short_name()},

Your password was successfully changed on {changed_at}.

Device: {device}
IP Address: {ip_address}

If you made this change, you can ignore this email.

If you did NOT make this change, your account may be compromised.
Please reset your password immediately:
{settings.FRONTEND_URL}/forgot-password

— Skincare App Security Team
        """.strip()

        html_content = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="500" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.07);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#dc2626,#7c3aed);padding:40px;text-align:center;">
              <div style="font-size:40px;margin-bottom:10px;">🔐</div>
              <h1 style="color:#ffffff;margin:0;font-size:24px;font-weight:bold;">
                Password Changed
              </h1>
              <p style="color:#fca5a5;margin:8px 0 0;font-size:14px;">Security Alert — Skincare App</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px;">
              <p style="color:#374151;font-size:16px;margin:0 0 8px;">
                Hi <strong>{user.get_short_name()}</strong>,
              </p>
              <p style="color:#6b7280;font-size:15px;margin:0 0 24px;">
                Your account password was successfully changed.
              </p>

              <!-- Details Box -->
              <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:24px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                      <span style="color:#9ca3af;font-size:13px;">📅 Date & Time</span><br>
                      <span style="color:#111827;font-size:14px;font-weight:600;">{changed_at}</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                      <span style="color:#9ca3af;font-size:13px;">🌐 IP Address</span><br>
                      <span style="color:#111827;font-size:14px;font-weight:600;">{ip_address}</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;">
                      <span style="color:#9ca3af;font-size:13px;">💻 Device</span><br>
                      <span style="color:#111827;font-size:14px;font-weight:600;">{device}</span>
                    </td>
                  </tr>
                </table>
              </div>

              <!-- If you did this -->
              <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;margin-bottom:16px;">
                <p style="color:#166534;font-size:13px;margin:0;">
                  ✅ <strong>This was you?</strong> No action needed. You're all set!
                </p>
              </div>

              <!-- If you didn't -->
              <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:16px;margin-bottom:24px;">
                <p style="color:#991b1b;font-size:13px;margin:0 0 12px;">
                  ⚠️ <strong>Wasn't you?</strong> Your account may be compromised. Reset your password immediately!
                </p>
                <a href="{settings.FRONTEND_URL}/forgot-password"
                   style="display:inline-block;background:#dc2626;color:#ffffff;
                          text-decoration:none;font-size:13px;font-weight:bold;
                          padding:10px 24px;border-radius:8px;">
                  Reset Password Now →
                </a>
              </div>

              <p style="color:#9ca3af;font-size:12px;margin:0;text-align:center;">
                All existing sessions have been logged out for your security.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f9fafb;padding:24px;text-align:center;border-top:1px solid #f3f4f6;">
              <p style="color:#9ca3af;font-size:12px;margin:0;">— Skincare App Security Team</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        logger.info("Password change alert email sent to %s", user.email)
        return True

    except Exception as e:
        logger.error("Failed to send password change email to %s: %s", user.email, str(e))
        return False