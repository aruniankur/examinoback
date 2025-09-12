import os
import time
import razorpay
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Request, Depends
import json
import razorpay.errors
from typing import Dict, Any
from routes.auth import verify_token
from routes.database import user
from datetime import datetime

load_dotenv()
KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # optional, for webhooks

# Initialize Razorpay client
if not KEY_ID or not KEY_SECRET:
    raise ValueError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in environment variables")

razorpay_client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))

router = APIRouter(prefix="/payment", tags=["payment"])


class CreateOrderReq(BaseModel):
    amount: int        # amount in smallest currency unit (e.g., paise if INR)
    currency: str = "INR"
    receipt: str | None = None
    notes: dict | None = None

class PromocodeReq(BaseModel):
    promocode: str

prompodict = {
    "PROMOCODE10": 10,
    "GET50":50,
    "SUDUKOARUNI":98,
}

@router.post("/promocode")
async def promocode(req: PromocodeReq, current_user: str = Depends(verify_token)):
    try:
        # print(f"Promocode for user: {current_user}")
        # print(f"Promocode: {req.promocode}")
        discount = prompodict[req.promocode]
        return {"status": "ok", "discount": discount}
    except Exception as e:
        print(f"Error in promocode for user {current_user}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid promocode: {req.promocode}")

@router.get("/pastpaymentinfo")
async def payment_info(current_user: str = Depends(verify_token)):
    try:
        userinfo = user.find_one({"email": current_user})
        if not userinfo:
            raise HTTPException(status_code=404, detail="User not found")
        print('--------------------------------')
        print(userinfo.get("payment_info", []))
        return {"status": "ok", "payment_info": userinfo.get("payment_info", []),"name": userinfo.get("name", None),"email": userinfo.get("email", None),"MobileNumber": userinfo.get("MobileNumber", None)}
    except Exception as e:
        print(f"Error in payment info for user {current_user}: {str(e)}")

@router.post("/create-order")
async def create_order(req: CreateOrderReq, current_user: str = Depends(verify_token)):
    """
    Create a new Razorpay order for payment processing.
    Requires JWT authentication.
    """
    print(f"Creating order for user: {current_user}")
    try:
        # Razorpay expects amount in paise for INR (so 100 = ₹1.00)
        data = {
            "amount": req.amount,
            "currency": req.currency,
            "receipt": req.receipt or f"receipt_{current_user}_{int(time.time())}",
            "payment_capture": 1,  # 1 = auto-capture, 0 = manual capture
            "notes": {
                "user_email": current_user,
                **(req.notes or {})
            }
        }
        
        # Create order using Razorpay API
        print(data)
        order = razorpay_client.order.create(data=data)  # type: ignore
        
        # Log order creation for user
        print(f"Order created for user: {current_user}")
        print(f"Order ID: {order['id']}")
        print(f"Amount: {order['amount']}")
        
        # return order id and key to initialize checkout on client
        return {"order_id": order["id"], "razorpay_key": KEY_ID, "order": order}
    except Exception as e:
        print(f"Error creating order for user {current_user}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to create order: {str(e)}")


# Endpoint for checkout handler to POST the payment result and verify signature
class VerifyPaymentReq(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


@router.post("/verify-payment")
async def verify_payment(payload: VerifyPaymentReq, current_user: str = Depends(verify_token)):
    """
    Verify payment signature and fetch payment details.
    Requires JWT authentication.
    """
    try:
        # Build dict exactly as Razorpay expects
        params_dict = {
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature
        }
        
        # Verify payment signature using Razorpay utility
        razorpay_client.utility.verify_payment_signature(params_dict)  # type: ignore
        
        # signature valid -> payment authentic
        # Fetch payment details from Razorpay API
        payment = razorpay_client.payment.fetch(payload.razorpay_payment_id)  # type: ignore
        print(payment)
        # Log payment verification for user
        print(f"Payment verified for user: {current_user}")
        print(f"Payment ID: {payload.razorpay_payment_id}")
        print(f"Order ID: {payload.razorpay_order_id}")
        print(f"Amount: {payment.get('amount', 'N/A')}")
        enddate = payment['notes']['endDate']
        print(f"enddate: {payment['notes']['endDate']}")
        dt = datetime.strptime(enddate, "%Y-%m-%d")
        timestamp = dt.timestamp()
        print("Date string:", enddate)
        print("As timestamp:", timestamp)
        # TODO: persist payment/order in DB, send receipt, etc.
        # You can add database operations here to store payment information
        # associated with the current_user
        user.update_one({"email": current_user}, {"$set": {"subscription": "Pro", "subscription_end_date": timestamp, "trail": 9999}, "$push": {"payment_info": payment}})
        
        return {"status": "ok", "payment": payment['id']}
    except razorpay.errors.SignatureVerificationError:
        print(f"Invalid signature for user {current_user}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"Payment verification failed for user {current_user}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Payment verification failed: {str(e)}")