from dataclasses import dataclass
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


@dataclass(frozen=True)
class OtpEmailTemplate:
    subject: str
    badge_label: str
    badge_color: str
    badge_bg: str
    badge_border: str
    heading: str
    purpose_label: str
    summary: str
    ignore_note: str


_OTP_TEMPLATES: dict[str, OtpEmailTemplate] = {
    "registration": OtpEmailTemplate(
        subject="MLOps PaaS — Account Registration Code",
        badge_label="ACCOUNT REGISTRATION",
        badge_color="#1d4ed8",
        badge_bg="#eff6ff",
        badge_border="#bfdbfe",
        heading="Verify your email to create your account",
        purpose_label="New Account Registration",
        summary=(
            "Use the one-time verification code below to confirm your email address "
            "and complete your MLOps PaaS registration."
        ),
        ignore_note=(
            "If you did not try to create an account on MLOps PaaS, "
            "you can safely ignore this email."
        ),
    ),
    "password_reset": OtpEmailTemplate(
        subject="MLOps PaaS — Forgot Password Reset Code",
        badge_label="FORGOT PASSWORD",
        badge_color="#b45309",
        badge_bg="#fffbeb",
        badge_border="#fde68a",
        heading="Reset your forgotten password",
        purpose_label="Forgot Password Recovery",
        summary=(
            "We received a request to recover access to your MLOps PaaS account. "
            "Enter the verification code below to set a new password."
        ),
        ignore_note=(
            "If you did not request a password reset, no changes have been made to your account "
            "and you can safely ignore this email."
        ),
    ),
    "password_change": OtpEmailTemplate(
        subject="MLOps PaaS — Password Change Verification Code",
        badge_label="PASSWORD CHANGE",
        badge_color="#b91c1c",
        badge_bg="#fef2f2",
        badge_border="#fecaca",
        heading="Confirm your account password change",
        purpose_label="Change Account Password (Profile Settings)",
        summary=(
            "You initiated a password change from your signed-in MLOps PaaS Profile Settings. "
            "Enter the verification code below to authorize this security update."
        ),
        ignore_note=(
            "If you did NOT request a password change while signed in, secure your account immediately "
            "by updating your password and revoking any unfamiliar API keys."
        ),
    ),
}


def _template_for_purpose(purpose: str) -> OtpEmailTemplate:
    if purpose in _OTP_TEMPLATES:
        return _OTP_TEMPLATES[purpose]
    label = purpose.replace("_", " ").strip() or "verification"
    return OtpEmailTemplate(
        subject=f"MLOps PaaS — {label.title()} Code",
        badge_label=label.upper(),
        badge_color="#334155",
        badge_bg="#f1f5f9",
        badge_border="#cbd5e1",
        heading=f"Your {label} verification code",
        purpose_label=label.title(),
        summary="Enter the one-time verification code below to complete your request.",
        ignore_note="If you did not initiate this request, you can safely ignore this email.",
    )


def _sender_address() -> str | None:
    host_user = getattr(settings, "EMAIL_HOST_USER", "")
    if host_user:
        return f"MLOps PaaS <{host_user}>"
    return None


def _render_plain_text(
    *,
    template: OtpEmailTemplate,
    code: str,
    recipient: str,
    ttl_minutes: int,
    max_attempts: int,
) -> str:
    return (
        f"MLOps PaaS — {template.purpose_label}\n"
        f"{'=' * 48}\n\n"
        f"{template.heading}\n\n"
        f"{template.summary}\n\n"
        f"Verification Code: {code}\n"
        f"Action:            {template.purpose_label}\n"
        f"Account Email:     {recipient}\n"
        f"Expires In:        {ttl_minutes} minutes (single-use, max {max_attempts} attempts)\n\n"
        f"Security Notice:\n"
        f"- Never share this verification code with anyone.\n"
        f"- {template.ignore_note}\n"
    )


def _render_html(
    *,
    template: OtpEmailTemplate,
    code: str,
    recipient: str,
    ttl_minutes: int,
    max_attempts: int,
) -> str:
    safe_code = escape(code)
    safe_recipient = escape(recipient)
    safe_badge = escape(template.badge_label)
    safe_heading = escape(template.heading)
    safe_purpose = escape(template.purpose_label)
    safe_summary = escape(template.summary)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escape(template.subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    {safe_purpose} — Code: {safe_code} (expires in {ttl_minutes} minutes)
  </div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f1f5f9;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background-color:#ffffff;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 4px 12px rgba(15,23,42,0.06);">
          <tr>
            <td style="background-color:#0f172a;padding:22px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="font-size:20px;font-weight:700;letter-spacing:-0.02em;color:#f8fafc;">
                    <span style="color:#38bdf8;">ML</span><span style="font-style:italic;color:#f8fafc;">life</span>
                  </td>
                  <td align="right" style="font-size:12px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;">
                    Security Verification
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:28px;">
              <div style="margin-bottom:16px;">
                <span style="display:inline-block;padding:5px 12px;border-radius:9999px;font-size:11px;font-weight:700;letter-spacing:0.06em;color:{template.badge_color};background-color:{template.badge_bg};border:1px solid {template.badge_border};">
                  {safe_badge}
                </span>
              </div>
              <h1 style="margin:0 0 12px 0;font-size:22px;line-height:1.3;font-weight:700;color:#0f172a;">
                {safe_heading}
              </h1>
              <p style="margin:0 0 24px 0;font-size:15px;line-height:1.6;color:#475569;">
                {safe_summary}
              </p>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:24px;background-color:#f8fafc;border:1px dashed #cbd5e1;border-radius:10px;">
                <tr>
                  <td align="center" style="padding:24px 16px;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#64748b;margin-bottom:10px;">
                      One-Time Verification Code
                    </div>
                    <div style="font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:34px;font-weight:800;letter-spacing:10px;color:#0f172a;padding-left:10px;">
                      {safe_code}
                    </div>
                    <div style="margin-top:12px;font-size:12px;color:#64748b;">
                      Expires in <strong style="color:#0f172a;">{ttl_minutes} minutes</strong> &middot; Single-use &middot; Max {max_attempts} attempts
                    </div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:22px;border-collapse:collapse;font-size:13px;">
                <tr>
                  <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;color:#64748b;width:130px;">Purpose</td>
                  <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;font-weight:600;color:#0f172a;">{safe_purpose}</td>
                </tr>
                <tr>
                  <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;color:#64748b;">Account Email</td>
                  <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;font-weight:600;color:#0f172a;">{safe_recipient}</td>
                </tr>
                <tr>
                  <td style="padding:8px 0;color:#64748b;">Validity</td>
                  <td style="padding:8px 0;font-weight:600;color:#0f172a;">{ttl_minutes} minutes</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background-color:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;text-align:center;">
              Automated security notification from <strong style="color:#334155;">MLOps PaaS</strong>. Please do not reply to this email.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_otp_email(
    *,
    email: str,
    purpose: str,
    code: str,
    ttl_seconds: int,
    max_attempts: int,
) -> None:
    """Send a purpose-specific HTML and plain-text OTP verification email."""
    recipient = email.strip()
    template = _template_for_purpose(purpose)
    ttl_minutes = max(1, ttl_seconds // 60)

    text_body = _render_plain_text(
        template=template,
        code=code,
        recipient=recipient,
        ttl_minutes=ttl_minutes,
        max_attempts=max_attempts,
    )
    html_body = _render_html(
        template=template,
        code=code,
        recipient=recipient,
        ttl_minutes=ttl_minutes,
        max_attempts=max_attempts,
    )

    message = EmailMultiAlternatives(
        subject=template.subject,
        body=text_body,
        from_email=_sender_address(),
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
