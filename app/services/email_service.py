import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_email(to: List[str], subject: str, html_body: str, cc: List[str] = None):
    password = settings.SMTP_PASSWORD.replace(" ", "")
    cc = cc or []

    # Remove duplicates and empty strings
    to = list(set(filter(None, to)))
    cc = list(set(filter(None, [c for c in cc if c not in to])))

    if not to:
        print("❌ No recipient email provided")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.attach(MIMEText(html_body, "html"))

    all_recipients = to + cc

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, password)
        server.sendmail(settings.SMTP_FROM, all_recipients, msg.as_string())
        server.quit()
        print(f"✅ Email sent to {to}" + (f" (CC: {cc})" if cc else ""))
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Auth failed: {e}")
    except Exception as e:
        print(f"❌ Email error: {e}")


def send_welcome_email(employee_email: str, employee_name: str, company_email: str, temp_password: str):
    joining_link = f"{settings.FRONTEND_URL}/login?redirect=/joining-details"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
      <div style="background: linear-gradient(135deg, #0d5c7a, #1a8cad); padding: 36px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 26px;">🎉 Welcome to {settings.COMPANY_NAME}!</h1>
        <p style="color: rgba(255,255,255,0.85); margin: 10px 0 0; font-size: 15px;">Your HR Portal is ready — let's get you set up</p>
      </div>
      <div style="padding: 32px; background: #f9f9f9;">
        <p style="font-size: 16px; margin: 0 0 8px;">Dear <strong>{employee_name}</strong>,</p>
        <p style="color: #555; margin: 0 0 24px; line-height: 1.6;">
          You have been successfully onboarded to <strong>{settings.COMPANY_NAME}</strong>.
          Use the credentials below to log in and complete your joining details — including uploading your documents and filling in insurance information.
        </p>

        <!-- Credentials box -->
        <div style="background: white; padding: 24px; border-radius: 10px; border-left: 4px solid #1a8cad; margin-bottom: 24px;">
          <p style="margin: 0 0 14px; font-weight: 700; color: #0d5c7a; font-size: 14px;">🔑 Your Login Credentials</p>
          <table style="width: 100%; border-collapse: collapse;">
            <tr>
              <td style="padding: 8px 0; color: #888; font-size: 13px; width: 160px;">Portal URL</td>
              <td style="padding: 8px 0; font-weight: bold;"><a href="{settings.FRONTEND_URL}" style="color: #0d5c7a;">{settings.FRONTEND_URL}</a></td>
            </tr>
            <tr style="border-top: 1px solid #f0f0f0;">
              <td style="padding: 8px 0; color: #888; font-size: 13px;">Username</td>
              <td style="padding: 8px 0; font-weight: bold; font-family: monospace; font-size: 15px;">{company_email}</td>
            </tr>
            <tr style="border-top: 1px solid #f0f0f0;">
              <td style="padding: 8px 0; color: #888; font-size: 13px;">Temporary Password</td>
              <td style="padding: 8px 0; font-weight: bold; font-family: monospace; font-size: 15px; color: #e74c3c;">{temp_password}</td>
            </tr>
          </table>
        </div>

        <!-- Warning -->
        <div style="background: #fff8e1; padding: 14px 18px; border-radius: 8px; border-left: 3px solid #f59e0b; margin-bottom: 24px;">
          <p style="margin: 0; color: #92400e; font-size: 13px;">
            ⚠️ <strong>Important:</strong> This is your <strong>{settings.COMPANY_NAME} HR Portal</strong> login, not a Google or Gmail account.
            Open the portal URL and enter the username &amp; password above.
          </p>
        </div>

        <!-- Action Required box -->
        <div style="background: #e8f5e9; padding: 18px 20px; border-radius: 10px; border-left: 4px solid #4caf50; margin-bottom: 24px;">
          <p style="margin: 0 0 10px; font-weight: 700; color: #2e7d32; font-size: 14px;">📋 Action Required — Complete Your Joining Details</p>
          <p style="margin: 0 0 12px; color: #388e3c; font-size: 13px; line-height: 1.5;">
            After logging in, please visit your <strong>Joining Details</strong> page to:
          </p>
          <ul style="margin: 0 0 14px; padding-left: 20px; color: #2e7d32; font-size: 13px; line-height: 1.8;">
            <li>📄 Upload your required documents (Aadhar, PAN, etc.)</li>
            <li>🏥 Fill in your insurance &amp; nominee details</li>
            <li>💼 Add your previous work history</li>
          </ul>
          <a href="{joining_link}"
             style="display: inline-block; background: #2e7d32; color: white; padding: 11px 26px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 14px;">
            ✅ Complete Joining Details →
          </a>
        </div>

        <!-- Two CTA buttons -->
        <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px;">
          <a href="{settings.FRONTEND_URL}"
             style="display: inline-block; background: #0d5c7a; color: white; padding: 12px 26px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 14px;">
            🏠 Go to HR Portal
          </a>
          <a href="{joining_link}"
             style="display: inline-block; background: white; color: #0d5c7a; padding: 12px 26px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 14px; border: 2px solid #0d5c7a;">
            📋 Joining Details
          </a>
        </div>

        <p style="margin: 0; color: #888; font-size: 12px; line-height: 1.6;">
          Please change your password after your first login.<br>
          If you have any issues, contact HR at <a href="mailto:{settings.SMTP_FROM}" style="color:#0d5c7a;">{settings.SMTP_FROM}</a>
        </p>
      </div>
    </div>
    """
    _send_email([employee_email], f"Welcome to {settings.COMPANY_NAME} – Your HR Portal Access & Next Steps", html)


def send_relieving_notification(
    to_email: str,
    employee_name: str,
    employee_id: str,
    relieving_date: str,
    cc_emails: List[str] = None,
    department: str = "",
    role: str = "",
    onboarded_by_name: str = "",
):
    cc_section = ""
    if cc_emails:
        cc_section = f"<p style='font-size:12px;color:#888;'>HR Admins in CC: {', '.join(cc_emails)}</p>"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 12px; overflow: hidden;">
      <div style="background: #c0392b; padding: 24px; text-align: center;">
        <h2 style="color: white; margin: 0;">🚪 Employee Relieving Notice</h2>
      </div>
      <div style="padding: 28px; background: #f9f9f9;">
        <p style="font-size: 15px;">The following employee is being relieved from <strong>{settings.COMPANY_NAME}</strong>.</p>
        <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #c0392b; margin: 20px 0;">
          <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px 0; color: #888; font-size: 13px; width: 160px;">Employee Name</td><td style="padding: 8px 0; font-weight: bold; font-size: 15px;">{employee_name}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding: 8px 0; color: #888; font-size: 13px;">Employee ID</td><td style="padding: 8px 0; font-weight: bold;">{employee_id}</td></tr>
            {'<tr style="border-top:1px solid #f0f0f0;"><td style="padding: 8px 0; color: #888; font-size: 13px;">Department</td><td style="padding: 8px 0;">' + department + '</td></tr>' if department else ''}
            {'<tr style="border-top:1px solid #f0f0f0;"><td style="padding: 8px 0; color: #888; font-size: 13px;">Role</td><td style="padding: 8px 0;">' + role + '</td></tr>' if role else ''}
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding: 8px 0; color: #888; font-size: 13px;">Relieving Date</td><td style="padding: 8px 0; font-weight: bold; color: #c0392b; font-size: 15px;">{relieving_date}</td></tr>
            {'<tr style="border-top:1px solid #f0f0f0;"><td style="padding: 8px 0; color: #888; font-size: 13px;">Onboarded By</td><td style="padding: 8px 0;">' + onboarded_by_name + '</td></tr>' if onboarded_by_name else ''}
          </table>
        </div>
        <div style="background: #fff8e1; padding: 14px 18px; border-radius: 8px; border-left: 3px solid #f59e0b; margin-bottom: 16px;">
          <p style="margin: 0; font-weight: bold; color: #92400e;">📦 Action Required:</p>
          <ul style="margin: 8px 0 0; padding-left: 20px; color: #555; font-size: 13px;">
            <li>Collect all company assets (laptop, access card, ID card, etc.)</li>
            <li>Revoke system access and company email</li>
            <li>Process full and final settlement</li>
            <li>Conduct exit interview if applicable</li>
          </ul>
        </div>
        {cc_section}
      </div>
    </div>
    """
    _send_email([to_email], f"Relieving Notice — {employee_name} ({employee_id}) | {relieving_date}", html, cc=cc_emails)


def send_asset_allocation_email(
    hr_email: str,
    employee_name: str,
    employee_id: str,
    action: str,
    assets: List[str],
    cc_emails: List[str] = None,
    department: str = "",
    joining_date: str = "",
):
    action_text = "allocate to" if action == "allocate" else "collect from"
    color = "#0d5c7a" if action == "allocate" else "#c0392b"
    icon = "📦" if action == "allocate" else "📥"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 12px; overflow: hidden;">
      <div style="background: {color}; padding: 24px; text-align: center;">
        <h2 style="color: white; margin: 0;">{icon} Asset {action.title()} Request</h2>
      </div>
      <div style="padding: 28px; background: #f9f9f9;">
        <p style="font-size: 15px;">Please <strong>{action_text}</strong> the following assets:</p>
        <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid {color}; margin: 20px 0;">
          <p><strong>Employee:</strong> {employee_name}</p>
          <p><strong>ID:</strong> {employee_id}</p>
          {'<p><strong>Department:</strong> ' + department + '</p>' if department else ''}
          {'<p><strong>Joining Date:</strong> ' + joining_date + '</p>' if joining_date else ''}
          <hr style="border: none; border-top: 1px solid #eee; margin: 12px 0;"/>
          <p style="font-weight: bold; margin-bottom: 8px;">Assets:</p>
          <ul style="margin: 0; padding-left: 20px;">
            {"".join(f"<li style='margin-bottom:4px;'>{a}</li>" for a in assets)}
          </ul>
        </div>
      </div>
    </div>
    """
    _send_email([hr_email], f"Asset {action.title()} — {employee_name} ({employee_id})", html, cc=cc_emails)


def send_step_notification(hr_email, employee_name, employee_id, step, step_title, step_desc, note=None):
    steps_info = {
        1: ("📋", "#0d5c7a"), 2: ("💼", "#1a8cad"),
        3: ("📄", "#29b6e0"), 4: ("🚀", "#16a34a"),
    }
    icon, color = steps_info.get(step, ("✅", "#0d5c7a"))
    note_section = f"<p style='color:#555;font-size:13px;font-style:italic;'>Note: {note}</p>" if note else ""
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;border:1px solid #e0e0e0;border-radius:12px;overflow:hidden;">
      <div style="background:{color};padding:20px;text-align:center;">
        <span style="font-size:36px;">{icon}</span>
        <h2 style="color:white;margin:8px 0 0;">Onboarding Step {step}: {step_title}</h2>
      </div>
      <div style="padding:24px;background:#f9f9f9;">
        <p><strong>{employee_name}</strong> ({employee_id}) — {step_desc}.</p>
        {note_section}
        <div style="background:white;padding:14px;border-radius:8px;border-left:4px solid {color};margin-top:16px;">
          <p style="margin:0;font-size:13px;color:#555;">Onboarding progress: Step {step} of 4 completed.</p>
        </div>
      </div>
    </div>"""
    _send_email([hr_email], f"Onboarding Step {step}: {employee_name} — {step_title}", html)


def send_insurance_request(to_email, employee_name, employee_id, department, joining_date,
                            nominee_name, nominee_relation, blood_group, pre_existing,
                            smoking_status="", nominee_dob="", nominee_phone="",
                            spouse_name="", spouse_dob="", spouse_gender="",
                            children_info="  None"):
    def row(label, value, bold=False):
        val = f"<strong>{value}</strong>" if bold else value
        return (f'<tr style="border-top:1px solid #f0f0f0;">'
                f'<td style="padding:6px 0;color:#888;font-size:13px;width:160px;">{label}</td>'
                f'<td style="padding:6px 0;">{val or "—"}</td></tr>')

    spouse_section = ""
    if spouse_name:
        spouse_section = f"""
        <div style="background:white;padding:16px 20px;border-radius:10px;border-left:4px solid #0ea5e9;margin:12px 0;">
          <p style="margin:0 0 10px;font-weight:bold;color:#0369a1;">👫 Spouse Details</p>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:6px 0;color:#888;font-size:13px;width:160px;">Spouse Name</td><td style="padding:6px 0;font-weight:bold;">{spouse_name}</td></tr>
            {row("Date of Birth", spouse_dob)}
            {row("Gender", spouse_gender)}
          </table>
        </div>"""

    children_html_rows = ""
    if children_info and children_info.strip() != "None":
        lines = [l.strip().lstrip("• ").strip() for l in children_info.strip().splitlines() if l.strip()]
        for line in lines:
            children_html_rows += f'<tr style="border-top:1px solid #f0f0f0;"><td colspan="2" style="padding:6px 0;font-size:13px;">{line}</td></tr>'
        children_section = f"""
        <div style="background:white;padding:16px 20px;border-radius:10px;border-left:4px solid #f59e0b;margin:12px 0;">
          <p style="margin:0 0 10px;font-weight:bold;color:#b45309;">👶 Children</p>
          <table style="width:100%;border-collapse:collapse;">{children_html_rows}</table>
        </div>"""
    else:
        children_section = ""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e0e0e0;border-radius:12px;overflow:hidden;">
      <div style="background:#7c3aed;padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">🏥 Insurance Enrollment Request</h2>
      </div>
      <div style="padding:24px;background:#f9f9f9;">
        <p>Please process insurance enrollment for the following employee:</p>

        <div style="background:white;padding:16px 20px;border-radius:10px;border-left:4px solid #7c3aed;margin:12px 0;">
          <p style="margin:0 0 10px;font-weight:bold;color:#5b21b6;">👤 Employee Details</p>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:6px 0;color:#888;font-size:13px;width:160px;">Employee Name</td><td style="padding:6px 0;font-weight:bold;">{employee_name}</td></tr>
            {row("Employee ID", employee_id)}
            {row("Department", department)}
            {row("Joining Date", joining_date)}
            {row("Blood Group", blood_group or "—", bold=True)}
            {row("Smoking Status", smoking_status or "N/A")}
            {row("Pre-existing Conditions", pre_existing or "None")}
          </table>
        </div>

        <div style="background:white;padding:16px 20px;border-radius:10px;border-left:4px solid #10b981;margin:12px 0;">
          <p style="margin:0 0 10px;font-weight:bold;color:#065f46;">📋 Nominee Details</p>
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:6px 0;color:#888;font-size:13px;width:160px;">Nominee Name</td><td style="padding:6px 0;font-weight:bold;">{nominee_name or "—"}</td></tr>
            {row("Relation", nominee_relation)}
            {row("Date of Birth", nominee_dob)}
            {row("Phone", nominee_phone)}
          </table>
        </div>

        {spouse_section}
        {children_section}

        <p style="color:#888;font-size:12px;margin-top:20px;">
          Please collect the enrollment form, assign a policy number, and confirm coverage within 5 business days.
        </p>
      </div>
    </div>"""
    _send_email([to_email], f"Insurance Enrollment — {employee_name} ({employee_id})", html)


def send_joining_details_email(
    personal_email: str,
    employee_name: str,
    employee_id: str,
    username: str,
    temp_password: str,
    missing_items: list,
    portal_url: str = None,
):
    """Send email to employee's personal email asking them to complete documents/insurance."""
    url = portal_url or settings.FRONTEND_URL
    login_base   = f"{url}/login?redirect=/joining-details"
    doc_link     = f"{url}/login?redirect=/joining-details%3Ftab%3Ddocuments"
    ins_link     = f"{url}/login?redirect=/joining-details%3Ftab%3Dinsurance"
    wh_link      = f"{url}/login?redirect=/joining-details%3Ftab%3Dwork-history"
    joining_link = f"{url}/login?redirect=/joining-details"

    missing_items_with_links = []
    for item in missing_items:
        if 'Document' in item or 'document' in item:
            missing_items_with_links.append((item, doc_link))
        elif 'Insurance' in item or 'insurance' in item:
            missing_items_with_links.append((item, ins_link))
        else:
            missing_items_with_links.append((item, joining_link))

    missing_html = "".join(
        f"<li style='margin-bottom:8px;padding:8px 12px;background:#fff3cd;border-radius:6px;display:flex;justify-content:space-between;align-items:center;'>"
        f"<span>⚠️ {item}</span>"
        f"<a href='{link}' style='font-size:12px;color:#0d5c7a;font-weight:bold;text-decoration:none;white-space:nowrap;margin-left:12px;'>→ Fill Now</a>"
        f"</li>"
        for item, link in missing_items_with_links
    )

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;border:1px solid #e0e0e0;border-radius:14px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
      <div style="background:linear-gradient(135deg,#0d5c7a,#1a8cad);padding:32px;text-align:center;">
        <h1 style="color:white;margin:0;font-size:24px;">📋 Action Required</h1>
        <p style="color:rgba(255,255,255,0.85);margin:10px 0 0;font-size:15px;">Please complete your joining details</p>
      </div>
      <div style="padding:32px;background:#f9f9f9;">
        <p style="font-size:15px;">Dear <strong>{employee_name}</strong>,</p>
        <p style="color:#555;line-height:1.6;">
          Your onboarding at <strong>{settings.COMPANY_NAME}</strong> is in progress. However, some important
          details are still pending. Please log in to the HR portal to complete them at your earliest convenience.
        </p>

        <div style="background:white;padding:20px;border-radius:10px;border-left:4px solid #f59e0b;margin:20px 0;">
          <p style="margin:0 0 10px;font-weight:bold;color:#92400e;">📌 Pending Items:</p>
          <ul style="margin:0;padding-left:0;list-style:none;">
            {missing_html}
          </ul>
        </div>

        <div style="background:white;padding:22px;border-radius:10px;border-left:4px solid #1a8cad;margin:20px 0;">
          <p style="margin:0 0 12px;font-weight:bold;color:#0d5c7a;">🔑 Your Login Credentials</p>
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="padding:8px 0;color:#888;font-size:13px;width:160px;">Portal URL</td>
              <td style="padding:8px 0;font-weight:bold;"><a href="{joining_link}" style="color:#0d5c7a;">{joining_link}</a></td>
            </tr>
            <tr style="border-top:1px solid #f0f0f0;">
              <td style="padding:8px 0;color:#888;font-size:13px;">Username</td>
              <td style="padding:8px 0;font-weight:bold;font-family:monospace;font-size:15px;">{username}</td>
            </tr>
            <tr style="border-top:1px solid #f0f0f0;">
              <td style="padding:8px 0;color:#888;font-size:13px;">Password</td>
              <td style="padding:8px 0;font-weight:bold;font-family:monospace;font-size:15px;color:#e74c3c;">{temp_password}</td>
            </tr>
            <tr style="border-top:1px solid #f0f0f0;">
              <td style="padding:8px 0;color:#888;font-size:13px;">Employee ID</td>
              <td style="padding:8px 0;font-weight:bold;">{employee_id}</td>
            </tr>
          </table>
        </div>

        <div style="background:#e8f5e9;padding:14px 18px;border-radius:8px;border-left:3px solid #4caf50;margin-bottom:20px;">
          <p style="margin:0;color:#2e7d32;font-size:13px;">
            ✅ <strong>Note:</strong> You can upload documents, fill insurance details, and add your work history.
            Other profile information is view-only. Contact HR if anything looks incorrect.
          </p>
        </div>

        <!-- Quick action buttons for each tab -->
        <p style="margin:0 0 10px;font-weight:bold;color:#0d5c7a;font-size:14px;">🚀 Jump directly to:</p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px;">
          <a href="{doc_link}" style="display:inline-block;background:#0d5c7a;color:white;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:13px;">
            📄 Upload Documents
          </a>
          <a href="{wh_link}" style="display:inline-block;background:#1a8cad;color:white;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:13px;">
            💼 Work History
          </a>
          <a href="{ins_link}" style="display:inline-block;background:#7c3aed;color:white;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:13px;">
            🏥 Insurance Details
          </a>
        </div>

        <a href="{joining_link}" style="display:inline-block;background:white;color:#0d5c7a;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:13px;border:2px solid #0d5c7a;margin-bottom:20px;">
          📋 View All Joining Details
        </a>

        <p style="margin-top:20px;color:#888;font-size:12px;">
          If you have any questions, contact HR at {settings.SMTP_FROM}<br>
          This link is specific to your account. Please do not share your credentials.
        </p>
      </div>
    </div>
    """
    _send_email(
        [personal_email],
        f"Action Required: Complete Your Joining Details — {settings.COMPANY_NAME}",
        html,
    )


def send_email_setup_request(to_email, employee_name, employee_id, company_email,
                              department, role, joining_date, requested_by):
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;border:1px solid #e0e0e0;border-radius:12px;overflow:hidden;">
      <div style="background:#0369a1;padding:20px;text-align:center;">
        <h2 style="color:white;margin:0;">📧 Company Email Setup Request</h2>
      </div>
      <div style="padding:24px;background:#f9f9f9;">
        <p>Please create the following company email account:</p>
        <div style="background:white;padding:20px;border-radius:10px;border-left:4px solid #0369a1;margin:16px 0;">
          <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:6px 0;color:#888;font-size:13px;width:160px;">Employee Name</td><td style="padding:6px 0;font-weight:bold;">{employee_name}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding:6px 0;color:#888;font-size:13px;">Employee ID</td><td style="padding:6px 0;">{employee_id}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding:6px 0;color:#888;font-size:13px;">Email to Create</td><td style="padding:6px 0;font-weight:bold;color:#0369a1;font-family:monospace;">{company_email}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding:6px 0;color:#888;font-size:13px;">Department</td><td style="padding:6px 0;">{department}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding:6px 0;color:#888;font-size:13px;">Role</td><td style="padding:6px 0;">{role}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding:6px 0;color:#888;font-size:13px;">Joining Date</td><td style="padding:6px 0;">{joining_date}</td></tr>
            <tr style="border-top:1px solid #f0f0f0;"><td style="padding:6px 0;color:#888;font-size:13px;">Requested By</td><td style="padding:6px 0;">{requested_by}</td></tr>
          </table>
        </div>
        <p style="font-size:12px;color:#888;">Please complete the email setup before the employee's joining date.</p>
      </div>
    </div>"""
    _send_email([to_email], f"Email Setup Request — {employee_name} | {company_email}", html)

def send_password_reset_email(personal_email: str, employee_name: str, reset_link: str):
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
      <div style="background: linear-gradient(135deg, #0d5c7a, #1a8cad); padding: 32px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">🔐 Password Reset Request</h1>
        <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0; font-size: 14px;">{settings.COMPANY_NAME} HR Portal</p>
      </div>
      <div style="padding: 32px; background: #f9f9f9;">
        <p style="font-size: 16px; margin: 0 0 8px;">Dear <strong>{employee_name}</strong>,</p>
        <p style="color: #555; margin: 0 0 24px; line-height: 1.6;">
          We received a request to reset your HR portal password. Click the button below to set a new password.
          This link is valid for <strong>30 minutes</strong>.
        </p>
        <div style="text-align: center; margin: 28px 0;">
          <a href="{reset_link}" style="display: inline-block; background: linear-gradient(135deg, #0d5c7a, #1a8cad); color: white; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: bold; font-size: 15px; letter-spacing: 0.3px;">
            🔑 Reset My Password
          </a>
        </div>
        <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 14px 16px; margin-top: 20px;">
          <p style="margin: 0; font-size: 13px; color: #856404;">
            ⚠️ If you did not request a password reset, please ignore this email.
            Your password will remain unchanged.
          </p>
        </div>
        <p style="margin-top: 20px; color: #888; font-size: 12px; text-align: center;">
          This link expires in 30 minutes. Contact HR if you need further help.
        </p>
      </div>
    </div>
    """
    _send_email(
        [personal_email],
        f"Password Reset Request — {settings.COMPANY_NAME} HR Portal",
        html,
    )


def send_profile_task_email(personal_email: str, employee_name: str, missing_fields: list, portal_link: str):
    fields_html = "".join(
        f'<li style="padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px;">• {field}</li>'
        for field in missing_fields
    )
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
      <div style="background: linear-gradient(135deg, #7c3aed, #4f46e5); padding: 32px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">📋 Action Required: Complete Your Profile</h1>
        <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0; font-size: 14px;">{settings.COMPANY_NAME} HR Portal</p>
      </div>
      <div style="padding: 32px; background: #f9f9f9;">
        <p style="font-size: 16px; margin: 0 0 8px;">Dear <strong>{employee_name}</strong>,</p>
        <p style="color: #555; margin: 0 0 16px; line-height: 1.6;">
          Your HR profile is incomplete. Please log in and fill in the following missing details:
        </p>
        <div style="background: white; padding: 16px 20px; border-radius: 10px; border-left: 4px solid #7c3aed; margin-bottom: 24px;">
          <ul style="margin: 0; padding: 0; list-style: none;">
            {fields_html}
          </ul>
        </div>
        <div style="text-align: center; margin: 20px 0;">
          <a href="{portal_link}" style="display: inline-block; background: linear-gradient(135deg, #7c3aed, #4f46e5); color: white; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: bold; font-size: 15px;">
            ✏️ Complete My Profile
          </a>
        </div>
        <p style="margin-top: 20px; color: #888; font-size: 12px; text-align: center;">
          Please complete these details at the earliest. Contact HR if you have questions.
        </p>
      </div>
    </div>
    """
    _send_email(
        [personal_email],
        f"Action Required: Complete Your Profile — {settings.COMPANY_NAME}",
        html,
    )