package com.example.project.api

import kotlinx.coroutines.delay

class MockApiService : ApiService {
    // Persistent state for mock mode
    private val reservations = mutableListOf<ReservationInfo>(
        ReservationInfo(
            reservation_id = "RES-101",
            spot_id = "S-42",
            lot_id = "1",
            status = "Confirmed",
            start_time = "2023-12-01T10:00:00",
            end_time = "2023-12-01T12:00:00",
            price_at_booking = 30.0
        )
    )

    override suspend fun createUser(request: CreateUserRequest): CreateUserResponse {
        delay(500)
        return CreateUserResponse(success = true, user_id = "mock_user_123", message = "User created (Mock)")
    }

    override suspend fun login(request: LoginRequest): LoginResponse {
        delay(500)
        if (request.username == "error") {
             return LoginResponse(success = false, message = "Invalid credentials (Mock)")
        }
        return LoginResponse(success = true, user_id = "mock_user_123", message = "Logged in (Mock)")
    }

    override suspend fun listParkingLots(): List<ParkingLotInfo> {
        delay(500)
        return listOf(
            ParkingLotInfo("1", "Downtown Plaza", "123 Main St"),
            ParkingLotInfo("2", "Airport North", "Terminal 1"),
            ParkingLotInfo("3", "Harbor View", "456 Bay Ave")
        )
    }

    override suspend fun searchLots(request: SearchRequest): SearchResponse {
        delay(800)
        return SearchResponse(
            results = request.lot_ids.map { id ->
                LotSearchResult(
                    lot_id = id,
                    available_spots = (5..20).random(),
                    price_per_hour = 15.0,
                    event_id = "mock_event_${System.currentTimeMillis()}"
                )
            }
        )
    }

    override suspend fun bookLot(request: BookingRequest): BookingResponse {
        delay(1000)
        if (request.is_booking) {
            val resId = "RES-${System.currentTimeMillis()}"
            val newRes = ReservationInfo(
                reservation_id = resId,
                spot_id = "S-${(1..100).random()}",
                lot_id = request.lot_id,
                status = "Confirmed",
                start_time = request.start_time,
                end_time = request.end_time,
                price_at_booking = request.price
            )
            reservations.add(newRes)
            return BookingResponse(
                success = true,
                spot_id = newRes.spot_id,
                reservation_id = resId
            )
        } else {
            return BookingResponse(success = true, message = "Outcome recorded (Mock)")
        }
    }

    override suspend fun getUserReservations(request: UserReservationsRequest): UserReservationsResponse {
        delay(500)
        return UserReservationsResponse(reservations = reservations.toList())
    }

    override suspend fun cancelReservation(request: CancelReservationRequest): CancelReservationResponse {
        delay(500)
        val removed = reservations.removeIf { it.reservation_id == request.reservation_id }
        return if (removed) {
            CancelReservationResponse(success = true, message = "Cancelled (Mock)")
        } else {
            CancelReservationResponse(success = false, message = "Reservation not found (Mock)")
        }
    }
}
