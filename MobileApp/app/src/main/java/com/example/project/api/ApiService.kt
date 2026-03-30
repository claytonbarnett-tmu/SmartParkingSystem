package com.example.project.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface ApiService {
    @POST("/users")
    suspend fun createUser(@Body request: CreateUserRequest): CreateUserResponse

    @POST("/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    @GET("/parking-lots")
    suspend fun listParkingLots(): List<ParkingLotInfo>

    @POST("/search")
    suspend fun searchLots(@Body request: SearchRequest): SearchResponse

    @POST("/book")
    suspend fun bookLot(@Body request: BookingRequest): BookingResponse

    @POST("/reservations")
    suspend fun getUserReservations(@Body request: UserReservationsRequest): UserReservationsResponse

    @POST("/cancel-reservation")
    suspend fun cancelReservation(@Body request: CancelReservationRequest): CancelReservationResponse
}
