from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from api.routes.auth import get_current_user
from models.user import User
from core.pipeline import FinSentinelPipeline
from api.deps import get_pipeline
from database.db_manager import DatabaseManager

router = APIRouter()
db = DatabaseManager()

@router.get("/summary")
def get_summary(
    current_user: User = Depends(get_current_user)
):
    summaries = db.get_vendor_summary(current_user.id)
    return {"summary": summaries}

@router.get("/anomalies")
def get_anomalies(
    current_user: User = Depends(get_current_user)
):
    invoices = db.get_all_invoices(current_user.id)
    anomalies = []
    for inv in invoices:
        anomaly_data = inv.metadata.get("anomaly")
        if anomaly_data and anomaly_data.get("is_anomaly"):
            anomalies.append({
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "vendor_name": inv.vendor_name,
                "total": inv.total,
                "anomaly": anomaly_data
            })
    return {"anomalies": anomalies}

@router.get("/documents/{invoice_id}/fields")
def get_document_fields(
    invoice_id: int,
    current_user: User = Depends(get_current_user)
):
    inv = db.get_invoice_by_id(invoice_id)
    if not inv or inv.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "invoice_number": inv.invoice_number,
        "vendor_name": inv.vendor_name,
        "subtotal": inv.subtotal,
        "tax": inv.tax,
        "total": inv.total,
        "metadata": inv.metadata
    }
