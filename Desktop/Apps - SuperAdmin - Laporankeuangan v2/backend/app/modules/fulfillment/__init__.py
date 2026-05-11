"""Fulfillment module — DeliveryOrder, GoodsReceipt, RMA.

Sits between order docs (SO/PO in sales/purchase modules) and invoice docs
(SI/PI also in sales/purchase). Handles the *physical* movement of goods,
delegating to InventoryService.post_movement() for stock + cost layer
accounting and AccountingService.post_system_journal() for the GL.
"""
