"""HTML email templates. Plain inline-styled HTML (no template engine)."""

from __future__ import annotations

from app.config import settings


def _layout(title: str, body: str) -> str:
    """Wrap body content in standard email layout with header/footer."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family:Arial,sans-serif;background:#f5f7fb;margin:0;padding:24px;color:#1f2937">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <div style="background:#1a56db;color:#fff;padding:20px 24px">
      <h1 style="margin:0;font-size:18px;font-weight:600">Kompak Accounting</h1>
    </div>
    <div style="padding:24px">
      {body}
    </div>
    <div style="padding:16px 24px;background:#f9fafb;color:#6b7280;font-size:12px;text-align:center;border-top:1px solid #e5e7eb">
      <p style="margin:0">{settings.SMTP_FROM_NAME} · <a href="{settings.APP_PUBLIC_URL}" style="color:#1a56db">{settings.APP_PUBLIC_URL.replace('https://', '').replace('http://', '')}</a></p>
      <p style="margin:4px 0 0">Email otomatis — mohon tidak membalas pesan ini.</p>
    </div>
  </div>
</body></html>"""


def _btn(label: str, url: str) -> str:
    return f'<a href="{url}" style="display:inline-block;padding:10px 20px;background:#1a56db;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;margin:8px 0">{label}</a>'


def _fmt_rp(amount) -> str:
    try:
        return f"Rp {float(amount):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "Rp 0"


# ─── Welcome email ──────────────────────────────────────────────────────
def welcome_email(user_name: str, tenant_name: str, login_url: str | None = None) -> tuple[str, str]:
    subject = f"Selamat datang di Kompak Accounting, {user_name}!"
    body = f"""
    <h2 style="margin:0 0 16px;color:#1a56db">Halo, {user_name}!</h2>
    <p>Akun untuk <strong>{tenant_name}</strong> telah berhasil dibuat di Kompak Accounting.</p>
    <p>Anda sekarang dapat mengelola Chart of Accounts, transaksi, invoice, inventaris, dan laporan keuangan dari satu dashboard yang terintegrasi.</p>
    {_btn('Mulai Sekarang', login_url or settings.APP_PUBLIC_URL)}
    <p style="margin-top:24px;color:#6b7280;font-size:13px">Jika Anda tidak membuat akun ini, abaikan email ini.</p>
    """
    return subject, _layout(subject, body)


# ─── Invoice posted (to customer) ───────────────────────────────────────
def invoice_posted_email(
    customer_name: str, invoice_no: str, total: float, due_date: str | None,
    tenant_name: str, view_url: str | None = None,
) -> tuple[str, str]:
    subject = f"Invoice {invoice_no} dari {tenant_name}"
    due_html = f"<tr><td style='padding:6px 0'><strong>Jatuh Tempo</strong></td><td>{due_date}</td></tr>" if due_date else ""
    body = f"""
    <h2 style="margin:0 0 16px;color:#1a56db">Invoice Baru</h2>
    <p>Halo <strong>{customer_name}</strong>,</p>
    <p>Berikut detail invoice yang diterbitkan oleh <strong>{tenant_name}</strong>:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px">
      <tr><td style="padding:6px 0"><strong>No. Invoice</strong></td><td>{invoice_no}</td></tr>
      <tr><td style="padding:6px 0"><strong>Total</strong></td><td><strong style="color:#1a56db;font-size:16px">{_fmt_rp(total)}</strong></td></tr>
      {due_html}
    </table>
    {_btn('Lihat Invoice', view_url) if view_url else ''}
    <p style="margin-top:16px">Mohon lakukan pembayaran sebelum jatuh tempo. Terima kasih.</p>
    """
    return subject, _layout(subject, body)


# ─── Payment received (receipt) ─────────────────────────────────────────
def payment_received_email(
    customer_name: str, payment_no: str, amount: float, payment_date: str,
    tenant_name: str,
) -> tuple[str, str]:
    subject = f"Pembayaran diterima — {payment_no}"
    body = f"""
    <h2 style="margin:0 0 16px;color:#16a34a">✓ Pembayaran Diterima</h2>
    <p>Halo <strong>{customer_name}</strong>,</p>
    <p>Kami telah menerima pembayaran Anda. Terima kasih!</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px">
      <tr><td style="padding:6px 0"><strong>No. Pembayaran</strong></td><td>{payment_no}</td></tr>
      <tr><td style="padding:6px 0"><strong>Tanggal</strong></td><td>{payment_date}</td></tr>
      <tr><td style="padding:6px 0"><strong>Jumlah</strong></td><td><strong style="color:#16a34a;font-size:16px">{_fmt_rp(amount)}</strong></td></tr>
      <tr><td style="padding:6px 0"><strong>Penerima</strong></td><td>{tenant_name}</td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px;margin-top:16px">Email ini berfungsi sebagai bukti penerimaan resmi.</p>
    """
    return subject, _layout(subject, body)


# ─── Report ready ───────────────────────────────────────────────────────
def report_ready_email(
    user_name: str, report_type: str, fmt: str, download_url: str,
) -> tuple[str, str]:
    type_labels = {
        "trial-balance": "Neraca Saldo",
        "profit-loss":   "Laporan Laba Rugi",
        "balance-sheet": "Neraca",
        "cash-flow":     "Laporan Arus Kas",
        "aged-receivables": "Aged Receivables",
        "aged-payables":    "Aged Payables",
        "ppn":           "Laporan PPN",
    }
    label = type_labels.get(report_type, report_type)
    subject = f"Laporan siap — {label}"
    body = f"""
    <h2 style="margin:0 0 16px;color:#1a56db">Laporan Anda Siap</h2>
    <p>Halo {user_name},</p>
    <p>Laporan <strong>{label}</strong> dalam format <strong>{fmt.upper()}</strong> telah selesai diproses.</p>
    {_btn(f'Download {fmt.upper()}', download_url)}
    <p style="margin-top:16px;color:#6b7280;font-size:13px">Link download berlaku selama 1 jam.</p>
    """
    return subject, _layout(subject, body)


# ─── Password reset ─────────────────────────────────────────────────────
def password_reset_email(user_name: str, reset_url: str) -> tuple[str, str]:
    subject = "Reset Password Akun Anda"
    body = f"""
    <h2 style="margin:0 0 16px;color:#1a56db">Reset Password</h2>
    <p>Halo {user_name},</p>
    <p>Kami menerima permintaan untuk mereset password akun Anda. Klik tombol di bawah untuk melanjutkan:</p>
    {_btn('Reset Password', reset_url)}
    <p style="margin-top:16px;color:#6b7280;font-size:13px">Link berlaku selama 30 menit. Jika Anda tidak meminta reset, abaikan email ini.</p>
    """
    return subject, _layout(subject, body)
