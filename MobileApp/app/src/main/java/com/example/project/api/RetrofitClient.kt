package com.example.project.api

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit

object RetrofitClient {
    private const val BASE_URL = "http://10.0.2.2:8000"

    // Toggle this to true to use the mock API instead of the real backend
    var useMockMode: Boolean = false

    private val json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
    }

    private val realApiService: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(ApiService::class.java)
    }

    private val mockApiService: ApiService by lazy {
        MockApiService()
    }

    val apiService: ApiService
        get() = if (useMockMode) mockApiService else realApiService
}
