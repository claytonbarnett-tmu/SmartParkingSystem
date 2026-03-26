# gRPC client for Pricing Service


import os
from typing import Optional
import grpc
from pricing_service.pricing.generated import pricing_pb2, pricing_pb2_grpc

class PricingClient:
    def __init__(self, grpc_host: Optional[str] = None, grpc_port: Optional[int] = None):
        grpc_host = grpc_host or os.getenv("PRICING_GRPC_HOST", "localhost")
        grpc_port = grpc_port or int(os.getenv("PRICING_GRPC_PORT", 50052))
        self.channel = grpc.insecure_channel(f"{grpc_host}:{grpc_port}")
        self.stub = pricing_pb2_grpc.PricingServiceStub(self.channel)

    def get_price(self, lot_id: int, user_id: str, start_time: str, end_time: str) -> tuple[float, str]:
        request = pricing_pb2.GetPriceRequest(
            lot_id=str(lot_id),
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            occupancy_rate=0.0,  # Optional, set as needed
        )
        response = self.stub.GetPrice(request)
        # Use total_price as price_per_hour for prototype simplicity
        return (response.total_price, response.event_id)
