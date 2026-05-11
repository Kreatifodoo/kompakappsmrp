# Workflow ERP: Sales Order → Delivery → Invoice (+ Returns)

Dokumen ini menjelaskan workflow dokumen pesanan, pengiriman, dan retur yang
ditambahkan di Sprint A–E. Berlaku untuk tenant Kompak Accounting yang ingin
audit trail granular per-dokumen dan partial fulfillment.

## Ringkasan Dokumen

| Singkatan | Nama                          | Tujuan                                    | Trigger Posting                  |
|-----------|-------------------------------|-------------------------------------------|----------------------------------|
| **SO**    | Sales Order                   | Komitmen pesanan customer (pre-delivery)  | Confirm (tidak ada journal)      |
| **PO**    | Purchase Order                | Komitmen pesanan ke supplier              | Confirm (tidak ada journal)      |
| **DO**    | Delivery Order                | Pengiriman fisik barang ke customer       | Stock-out + Dr COGS / Cr Inv     |
| **GR**    | Goods Receipt                 | Penerimaan fisik barang dari supplier     | Stock-in + Dr Inv / Cr GR-clearing |
| **SI**    | Sales Invoice (Customer Inv)  | Tagihan ke customer                       | Dr AR / Cr Revenue (+ stock di flexible) |
| **PI**    | Purchase Invoice (Vendor Bill)| Tagihan dari supplier                     | Dr Exp/Inv / Cr AP (+ stock di flexible) |
| **RMA**   | Return Merchandise Auth.      | Pengembalian barang (customer/supplier)   | Stock-flip + reverse journal     |

## Workflow Sales Lengkap

```
                                         ┌─ (opsional) RMA-IN dari DO posted
                                         │   stock kembali masuk
SO  ─┬─ confirm ─┬─ DO  ─ post ─→ stock keluar + Dr COGS / Cr Inventory
     │           │                │
     │           │                └─ (opsional) RMA-IN customer return
     │           │
     │           └─ SI  ─ post ─→ Dr AR / Cr Revenue
     │                              (stock juga di-out kalau flexible mode)
     │
     └─ cancel
```

### Strict vs Flexible mode

Setiap tenant punya field `fulfillment_mode`:

- **`flexible`** (default untuk tenant lama): SI auto-create stock movement
  saat di-post. DO/GR opsional. Cara lama tetap jalan.
- **`strict`** (default untuk tenant baru): SI **tidak** buat stock movement.
  Setiap SI dengan stock item **wajib** punya `do_id` yang mengacu ke DO
  posted. Stock cuma keluar lewat DO. Sama untuk PI ↔ GR.

Cek mode tenant via SQL:
```sql
SELECT fulfillment_mode FROM tenants WHERE id='<tenant_id>';
```

## Step-by-Step di UI

### A. Sales — happy path

1. Sidebar **Sales → Sales Order** → klik **Buat SO**.
2. Isi customer, tanggal, baris item (item, warehouse, qty, harga).
3. **Simpan + Confirm**. SO status = `confirmed`.
4. Di list, klik tombol **Buat DO**. Modal pre-fill semua line dengan
   `qty_delivered = remaining`. Boleh kirim sebagian (partial delivery).
5. **Simpan + Post**. Backend:
   - Buat stock movement keluar (`source='delivery_order'`).
   - Buat journal **Dr COGS / Cr Inventory** sebesar qty × avg_cost.
   - Update `qty_delivered` di SO line.
   - Recompute SO status → `partially_delivered` atau `fulfilled`.
6. Ulang step 4–5 untuk DO sisa kalau partial.
7. Buat Customer Invoice (SI) seperti biasa. Di strict mode wajib pilih DO posted
   sebagai `do_id`.

### B. Purchase — happy path

Sama persis, mirror:

1. Sidebar **Purchase → Purchase Order** → **Buat PO** → Confirm.
2. **Buat GR** dari list PO. Setiap line bisa override `unit_cost` (harga
   aktual di nota supplier mungkin beda dari PO).
3. **Simpan + Post**. Backend:
   - Stock masuk (`source='goods_receipt'`).
   - Journal **Dr Inventory / Cr GR-clearing** (Goods Received Not Invoiced).
4. Buat Vendor Bill (PI). Strict mode wajib `gr_id`. Journal PI = **Dr
   GR-clearing / Cr AP** (membersihkan akrual GR-clearing).

### C. Customer Return (RMA-IN)

1. Di list **Delivery Order** posted, klik **Buat RMA**.
2. Pilih line yang di-return + qty. Unit cost otomatis ambil dari DO line.
3. **Simpan + Post**. Backend:
   - Stock kembali masuk (`source='customer_return'`).
   - Journal **Dr Inventory / Cr COGS** (membalik COGS DO original).

### D. Supplier Return (RMA-OUT)

1. Di list **Goods Receipt** posted, klik **Buat RMA**.
2. Pilih line + qty.
3. **Simpan + Post**. Backend:
   - Stock keluar (`source='supplier_return'`).
   - Journal **Dr GR-clearing / Cr Inventory** (membalik GR original).

### E. Void

Void DO/GR/RMA membalik stock movement asli + memanggil reverse journal.
Counter SO/PO `qty_delivered`/`qty_received` di-roll back. Status sumber
otomatis turun dari `fulfilled` → `partially_*`.

## Account Mappings yang Dibutuhkan

Setiap tenant wajib punya mapping berikut di **Accounting → Account Mappings**:

| Key                 | Untuk                                  |
|---------------------|----------------------------------------|
| `ar`                | Piutang Usaha (SI posting)             |
| `ap`                | Hutang Usaha (PI posting)              |
| `sales_revenue`     | Penjualan (SI posting)                 |
| `cogs`              | HPP (DO + RMA customer_return)         |
| `inventory`         | Persediaan (semua stock-touching docs) |
| `gr_clearing`       | Akrual GR Not Invoiced (GR + PI strict + RMA supplier_return) |
| `tax_payable`       | PPN keluaran (SI bertax)               |
| `tax_receivable`    | PPN masukan (PI bertax)                |

Tanpa mapping ini, posting akan ditolak dengan error `Account mapping missing`.

## Dashboard KPIs Baru

Halaman Dashboard kini menampilkan 5 KPI pipeline (klik untuk navigate):

- **📋 Open Sales Order** — `draft + confirmed + partially_delivered`
- **🚚 Pending DO** — `draft`
- **📋 Open Purchase Order** — `draft + confirmed + partially_received`
- **📥 Pending GR** — `draft`
- **↩ Open RMA** — `draft`

KPI di-refresh otomatis tiap user navigate ke Dashboard.

## Realtime

WebSocket event yang dipublish backend dan didengar UI:

| Event                       | UI behavior                                         |
|-----------------------------|-----------------------------------------------------|
| `sales_order.confirmed`     | Refresh halaman SO + toast                          |
| `purchase_order.confirmed`  | Refresh halaman PO + toast                          |
| `delivery_order.posted`     | Refresh DO, SO, inventory pages + toast             |
| `delivery_order.voided`     | Refresh DO, SO, inventory + warning toast           |
| `goods_receipt.posted`      | Refresh GR, PO, inventory + toast                   |
| `goods_receipt.voided`      | Refresh GR, PO, inventory + warning toast           |
| `rma.posted`                | Refresh RMA, DO, GR, inventory + toast              |
| `rma.voided`                | Refresh RMA, inventory + warning toast              |

## API Reference (singkat)

Semua endpoint butuh JWT + scope sesuai (`sales.write`, `purchase.write`, `sales.post`, ...).

| Method | Path                                  |
|--------|---------------------------------------|
| GET    | `/api/v1/sales-orders`                |
| POST   | `/api/v1/sales-orders?confirm=true`   |
| POST   | `/api/v1/sales-orders/{id}/confirm`   |
| POST   | `/api/v1/sales-orders/{id}/cancel`    |
| GET    | `/api/v1/purchase-orders`             |
| POST   | `/api/v1/purchase-orders?confirm=true`|
| POST   | `/api/v1/delivery-orders?post_now=true`|
| POST   | `/api/v1/delivery-orders/{id}/post`   |
| POST   | `/api/v1/delivery-orders/{id}/void`   |
| POST   | `/api/v1/goods-receipts?post_now=true`|
| POST   | `/api/v1/goods-receipts/{id}/post`    |
| POST   | `/api/v1/goods-receipts/{id}/void`    |
| GET    | `/api/v1/rmas?rma_type=...`           |
| POST   | `/api/v1/rmas?post_now=true`          |
| POST   | `/api/v1/rmas/{id}/post`              |
| POST   | `/api/v1/rmas/{id}/void`              |

## Smoke Tests

- Sprint A (SO+DO):  9/9 PASS — `partial delivery + over-deliver reject + void rollback`
- Sprint B (PO+GR):  9/9 PASS — `partial receipt + over-receive reject + void rollback`
- Sprint C (RMA):    17/17 PASS — `customer + supplier return, journal verification, XOR validation`

Script test ada di `/tmp/rma_smoke.js` (versi terakhir) — login admin → eksekusi
full flow → verifikasi stock + journal.
