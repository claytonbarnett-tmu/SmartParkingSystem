package com.example.project.api

import kotlinx.serialization.Serializable

@Serializable
data class CreateUserRequest(
    val username: String,
    val email: String
)

@Serializable
data class CreateUserResponse(
    val success: Boolean,
    val user_id: String? = null,
    val message: String? = null
)

@Serializable
data class LoginRequest(
    val username: String,
    val email: String
)

@Serializable
data class LoginResponse(
    val success: Boolean,
    val user_id: String? = null,
    val message: String? = null
)

@Serializable
data class ParkingLotInfo(
    val id: String,
    val name: String,
    val address: String
)

@Serializable
data class SearchRequest(
    val user_id: String,
    val lot_ids: List<String>,
    val start_time: String,
    val end_time: String
)

@Serializable
data class LotSearchResult(
    val lot_id: String,
    val available_spots: Int,
    val price_per_hour: Double,
    val event_id: String
)

@Serializable
data class SearchResponse(
    val results: List<LotSearchResult>
)

@Serializable
data class BookingRequest(
    val user_id: String,
    val lot_id: String,
    val event_id: String,
    val start_time: String,
    val end_time: String,
    val price: Double,
    val is_booking: Boolean
)

@Serializable
data class BookingResponse(
    val success: Boolean,
    val spot_id: String? = null,
    val reservation_id: String? = null,
    val failure_reason: String? = null,
    val status: String? = null,
    val message: String? = null
)

@Serializable
data class UserReservationsRequest(
    val user_id: String
)

@Serializable
data class ReservationInfo(
    val reservation_id: String?,
    val spot_id: String?,
    val lot_id: String?,
    val status: String?,
    val start_time: String?,
    val end_time: String?,
    val price_at_booking: Double?
)

@Serializable
data class UserReservationsResponse(
    val reservations: List<ReservationInfo>
)

@Serializable
data class CancelReservationRequest(
    val user_id: String,
    val reservation_id: String
)

@Serializable
data class CancelReservationResponse(
    val success: Boolean,
    val message: String? = null
)
