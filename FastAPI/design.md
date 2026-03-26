# FastAPI Design Notes

## System Overview
- The Smart Parking System uses microservices for pricing and inventory, each exposing gRPC APIs.
- FastAPI will serve as a gateway between the frontend (REST) and backend (gRPC).

## Key Requirements
- Expose REST endpoints for the frontend/mobile app.
- Communicate with Pricing and Inventory services via gRPC.
- Focus for now: gRPC backend communication (REST for frontend can be added later).

## gRPC Service Contracts
### Pricing Service
- `GetPrice(lot_id, user_id, start_time, end_time)` → returns `price_per_hour`, `event_id`, etc.
- `RecordBookingOutcome(event_id, booked)` → returns success.
- Pricing service itself calls Inventory via gRPC for occupancy.

### Inventory Service
- `GetLotOccupancy(lot_id)` → returns occupancy stats.
- `ListSpots(lot_id)` → returns spot statuses.

## Design Considerations
- **Authentication/Authorization:** How will users be authenticated? Is there a user/session context to pass to gRPC?
- **Error Handling:** How should FastAPI handle gRPC errors or timeouts?
- **Data Mapping:** How to map REST request/response models to gRPC messages and vice versa?
- **Deployment:** Will FastAPI run in the same Docker network as the other services? How will service discovery work?
- **Testing:** What integration tests are needed for the gRPC layer?

## Next Steps
1. Set up FastAPI project structure.
2. Add gRPC client stubs for Pricing and Inventory (using generated Python code from .proto files).
3. Implement endpoints for:
   - Getting a price quote (calls PricingService.GetPrice)
   - Recording booking outcome (calls PricingService.RecordBookingOutcome)
   - (Optionally) exposing inventory info if needed for the frontend
4. Decide on error handling and logging strategy.
5. Document API and gRPC call flows.

## References
- See `pricing-service/DESIGN.md`, `pricing-service/INTEGRATION.md`, `inventory-service/DESIGN.md`, and the .proto files for detailed contracts and flows.
