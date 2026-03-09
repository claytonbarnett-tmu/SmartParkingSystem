from fastapi import FastAPI, HTTPException, Query

from inventory import service

from inventory.schemas import (
    Lot,
    Occupancy,
    ReservationRequest,
    ReservationResponse,
    Spot,
)

app = FastAPI(title="Smart Parking Inventory Service")

@app.on_event("startup")
def _startup() -> None:
    service.get_lot_occupancy(lot_id=0)


@app.get("/lots", response_model=list[Lot])
def list_lots() -> list[Lot]:
    return service.list_lots()


@app.get("/lots/{lot_id}/occupancy", response_model=Occupancy)
def get_occupancy(lot_id: int) -> Occupancy:
    occupancy = service.get_lot_occupancy(lot_id)
    if occupancy["total_spots"] == 0:
        raise HTTPException(status_code=404, detail="Lot not found")
    return occupancy


@app.get("/lots/{lot_id}/spots", response_model=list[Spot])
def list_spots(lot_id: int, status: str | None = Query(None)) -> list[Spot]:
    try:
        return service.list_spots(lot_id=lot_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(req: ReservationRequest) -> ReservationResponse:
    try:
        res = service.reserve_spot(
            user_id=req.user_id,
            lot_id=req.lot_id,
            spot_id=req.spot_id,
            start_time=req.start_time,
            end_time=req.end_time,
            price_at_booking=req.price_at_booking,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ReservationResponse(
        reservation_id=res.reservation_id,
        spot_id=res.spot_id,
        lot_id=res.lot_id,
        user_id=res.user_id,
        status=res.status,
        start_time=res.start_time,
        end_time=res.end_time,
        price_at_booking=float(res.price_at_booking) if res.price_at_booking is not None else None,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
