"""WhatsApp Webhook & Invoicing Router (Phases 17 & 18)."""

from fastapi import APIRouter, Request, Response, HTTPException, Query, Form
from pydantic import BaseModel, Field
from typing import Any

from app.services.whatsapp_service import (
    handle_incoming_whatsapp_message,
    send_whatsapp_message,
    format_whatsapp_invoice,
    get_outbound_messages_log,
)
from app.services.sales_service import get_sale_by_invoice
from app.config import settings

router = APIRouter(prefix="/webhook/whatsapp", tags=["WhatsApp"])


class SendInvoiceRequest(BaseModel):
    recipient_phone: str = Field(..., description="Customer WhatsApp phone number e.g. '+919876543210'")


class IncomingWhatsAppJSONPayload(BaseModel):
    from_number: str = Field(..., description="Sender's phone number")
    message: str = Field(..., description="Message text or transcription")
    sender_role: str | None = Field(default=None, description="'mother', 'father', 'customer'")


@router.get("")
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
):
    """
    Phase 17: Meta WhatsApp Cloud API Webhook Handshake Verification.
    """
    verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "shop_assistant_verify_token")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Verification failed", status_code=403)


@router.post("")
async def receive_whatsapp_message(request: Request):
    """
    Phase 17: Multi-provider WhatsApp Webhook Receiver.
    Supports both JSON payloads (Meta Cloud API / direct test clients)
    and Form payloads (Twilio WhatsApp Webhook with TwiML responses).
    """
    content_type = request.headers.get("content-type", "")
    is_twilio_form = "application/x-www-form-urlencoded" in content_type

    from_number = ""
    message_text = ""
    sender_role = None

    if "application/json" in content_type:
        data = await request.json()
        from_number = data.get("from_number") or data.get("From", "")
        message_text = data.get("message") or data.get("Body", "")
        sender_role = data.get("sender_role")
    elif is_twilio_form:
        form_data = await request.form()
        from_number = str(form_data.get("From", ""))
        message_text = str(form_data.get("Body", ""))
        sender_role = str(form_data.get("role", "")) if "role" in form_data else None

        # Handle incoming voice note media from Twilio WhatsApp
        num_media = int(form_data.get("NumMedia", 0) or 0)
        is_media = num_media > 0 and bool(form_data.get("MediaUrl0"))
        if is_media:
            media_url = str(form_data.get("MediaUrl0"))
            try:
                import httpx
                from app.services.audio_service import transcribe_audio_bytes

                import os
                import logging
                logger = logging.getLogger(__name__)

                account_sid = os.getenv("TWILIO_ACCOUNT_SID") or settings.TWILIO_ACCOUNT_SID
                auth_token = os.getenv("TWILIO_AUTH_TOKEN") or settings.TWILIO_AUTH_TOKEN
                auth = (account_sid, auth_token) if (account_sid and auth_token) else None

                logger.info("Attempting to download Twilio voice note from: %s with SID %s", media_url, account_sid)
                async with httpx.AsyncClient() as http_client:
                    resp = await http_client.get(media_url, auth=auth, follow_redirects=True)
                    logger.info("Voice note download status: %d, length: %d bytes", resp.status_code, len(resp.content))
                    if resp.status_code == 200 and len(resp.content) > 0:
                        try:
                            transcribed = transcribe_audio_bytes(resp.content, filename="voice_note.ogg")
                            if transcribed:
                                message_text = transcribed
                                logger.info("Transcribed voice note to: '%s'", message_text)
                        except ValueError as ve:
                            reply_text = (
                                "🎙️ *Voice Note Received!*\n\n"
                                "To transcribe spoken audio, add your free `GEMINI_API_KEY` into `.env`:\n"
                                "👉 https://aistudio.google.com/app/apikey\n\n"
                                "💬 Or *type* your order as text:\n"
                                "*Kumar, 2 Scissor, 1 Kings*"
                            )
                            from xml.sax.saxutils import escape as xml_escape
                            twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(reply_text)}</Message></Response>'
                            return Response(content=twiml, media_type="application/xml")
                    else:
                        reply_text = (
                            "🎙️ *Voice Note Received!*\n\n"
                            f"Twilio download status: HTTP {resp.status_code}.\n"
                            "Could not download audio stream. You can type your orders directly (e.g. *Satya, 3 Filter, 1 Scissor*)."
                        )
                        from xml.sax.saxutils import escape as xml_escape
                        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(reply_text)}</Message></Response>'
                        return Response(content=twiml, media_type="application/xml")
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Failed to transcribe media note: %s", exc)
    else:
        # Fallback query / JSON
        try:
            data = await request.json()
            from_number = data.get("from_number", "")
            message_text = data.get("message", "")
        except Exception:
            raise HTTPException(status_code=400, detail="Unsupported Content-Type.")

    if not from_number:
        raise HTTPException(status_code=400, detail="Missing from_number or From phone number.")

    # If message text is empty, send helpful guide
    if not message_text.strip():
        reply_text = (
            "👋 *Welcome to Sri Murugan Stores Assistant!*\n\n"
            "Here is what you can do:\n"
            "• Create a bill: *Satya, 3 Filter, 1 Scissor, 2 Kings*\n"
            "• Search customer: *What did Satya buy today?*\n"
            "• Check sales: *What is today's total sales?*"
        )
        if is_twilio_form:
            from xml.sax.saxutils import escape as xml_escape
            twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(reply_text)}</Message></Response>'
            return Response(content=twiml, media_type="application/xml")
        return {"status": "success", "reply": reply_text}

    reply_text = handle_incoming_whatsapp_message(
        from_number=from_number,
        message_body=message_text,
        sender_role=sender_role,
    )

    # Return standard TwiML XML response for Twilio WhatsApp Webhook
    if is_twilio_form:
        from xml.sax.saxutils import escape as xml_escape
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(reply_text)}</Message></Response>'
        return Response(content=twiml, media_type="application/xml")

    return {"status": "success", "reply": reply_text}


@router.post("/send-invoice/{invoice_number}")
def send_customer_invoice_endpoint(invoice_number: str, payload: SendInvoiceRequest):
    """
    Phase 18: Send Confirmed Bill to Customer WhatsApp Number.
    Retrieves the confirmed transaction from MongoDB and delivers formatted invoice.
    """
    sale = get_sale_by_invoice(invoice_number)
    if not sale:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_number}' not found.")

    invoice_text = format_whatsapp_invoice(sale)
    dispatch_result = send_whatsapp_message(to_phone=payload.recipient_phone, message_text=invoice_text)
    return {
        "status": "sent",
        "invoice_number": invoice_number,
        "recipient": payload.recipient_phone,
        "message": invoice_text,
    }


@router.get("/logs")
def get_whatsapp_message_logs_endpoint():
    """Retrieve logged outbound WhatsApp messages for auditing."""
    return get_outbound_messages_log()
