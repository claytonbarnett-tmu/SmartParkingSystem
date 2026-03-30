package com.example.project

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import com.example.project.api.*
import com.example.project.ui.theme.ProjectTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ProjectTheme {
                AppNavigation()
            }
        }
    }
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    var currentUserId by remember { mutableStateOf<String?>(null) }
    var currentUsername by remember { mutableStateOf<String?>(null) }

    NavHost(navController = navController, startDestination = "login") {
        composable("login") {
            LoginScreen(
                onLoginSuccess = { userId, username ->
                    currentUserId = userId
                    currentUsername = username
                    navController.navigate("lot_list")
                }
            )
        }
        composable("lot_list") {
            ParkingLotListScreen(
                onLotSelected = { lotId -> navController.navigate("booking/$lotId") },
                onViewReservations = {
                    currentUserId?.let { navController.navigate("my_reservations/$it") }
                }
            )
        }
        composable(
            route = "booking/{lotId}",
            arguments = listOf(navArgument("lotId") { type = NavType.StringType })
        ) { backStackEntry ->
            val lotId = backStackEntry.arguments?.getString("lotId") ?: ""
            BookingScreen(
                lotId = lotId,
                userId = currentUserId ?: "",
                onReservationSuccess = { navController.navigate("success") },
                onBack = { navController.popBackStack() }
            )
        }
        composable("success") {
            ReservationSuccessScreen(
                onBackToHome = {
                    navController.navigate("lot_list") {
                        popUpTo("lot_list") { inclusive = true }
                    }
                },
                onViewReservations = {
                    currentUserId?.let { navController.navigate("my_reservations/$it") }
                }
            )
        }
        composable(
            route = "my_reservations/{userId}",
            arguments = listOf(navArgument("userId") { type = NavType.StringType })
        ) { backStackEntry ->
            val userId = backStackEntry.arguments?.getString("userId") ?: ""
            MyReservationsScreen(
                userId = userId,
                onBack = { navController.popBackStack() }
            )
        }
    }
}

@Composable
fun LoginScreen(onLoginSuccess: (String, String) -> Unit) {
    var username by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var isLoading by remember { mutableStateOf(false) }
    var isMockMode by remember { mutableStateOf(RetrofitClient.useMockMode) }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.Center
    ) {
        // Mock Mode Toggle
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Mock Mode", fontWeight = FontWeight.Medium, fontSize = 16.sp)
            Spacer(modifier = Modifier.width(12.dp))
            Switch(
                checked = isMockMode,
                onCheckedChange = {
                    isMockMode = it
                    RetrofitClient.useMockMode = it
                },
                modifier = Modifier.scale(1.4f), // Slightly bigger
                colors = SwitchDefaults.colors(
                    checkedThumbColor = Color.White,
                    checkedTrackColor = Color(0xFF87CEEB), // Light Blue (Sky Blue)
                    uncheckedThumbColor = Color.White,
                    uncheckedTrackColor = Color.LightGray
                )
            )
        }

        Spacer(modifier = Modifier.height(32.dp))

        Text("Smart Parking Login", fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Spacer(modifier = Modifier.height(16.dp))
        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Username") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(8.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(16.dp))
        Button(
            onClick = {
                scope.launch {
                    isLoading = true
                    try {
                        val response = RetrofitClient.apiService.login(LoginRequest(username, email))
                        if (response.success && response.user_id != null) {
                            onLoginSuccess(response.user_id, username)
                        } else {
                            // If login fails, try to create user (simplified flow)
                            val createResponse = RetrofitClient.apiService.createUser(CreateUserRequest(username, email))
                            if (createResponse.success && createResponse.user_id != null) {
                                onLoginSuccess(createResponse.user_id, username)
                            } else {
                                Toast.makeText(context, createResponse.message ?: "Login Failed", Toast.LENGTH_SHORT).show()
                            }
                        }
                    } catch (e: Exception) {
                        Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    } finally {
                        isLoading = false
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isLoading && username.isNotBlank() && email.isNotBlank()
        ) {
            if (isLoading) CircularProgressIndicator(modifier = Modifier.size(24.dp), color = MaterialTheme.colorScheme.onPrimary)
            else Text("Log in / Sign up")
        }
    }
}

@Composable
fun ParkingLotListScreen(onLotSelected: (String) -> Unit, onViewReservations: () -> Unit) {
    var lots by remember { mutableStateOf<List<ParkingLotInfo>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        try {
            lots = RetrofitClient.apiService.listParkingLots()
        } catch (e: Exception) {
            // Handle error
        } finally {
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            Row(
                modifier = Modifier
                    .statusBarsPadding()
                    .fillMaxWidth()
                    .padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Select a Parking Lot", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                IconButton(onClick = onViewReservations) {
                    Icon(Icons.AutoMirrored.Filled.List, contentDescription = "My Reservations")
                }
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(modifier = Modifier.padding(padding)) {
                items(lots) { lot ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(8.dp)
                            .clickable { onLotSelected(lot.id) }
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(lot.name, fontWeight = FontWeight.Bold)
                            Text(lot.address, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun BookingScreen(lotId: String, userId: String, onReservationSuccess: () -> Unit, onBack: () -> Unit) {
    var startDate by remember { mutableStateOf("2023-12-01") }
    var startTimeOnly by remember { mutableStateOf("10:00") }
    var endDate by remember { mutableStateOf("2023-12-01") }
    var endTimeOnly by remember { mutableStateOf("12:00") }

    var searchResults by remember { mutableStateOf<List<LotSearchResult>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var selectedResult by remember { mutableStateOf<LotSearchResult?>(null) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    val fullStartTime = "${startDate}T${startTimeOnly}:00"
    val fullEndTime = "${endDate}T${endTimeOnly}:00"

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .statusBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("Book a Spot", fontSize = 20.sp, fontWeight = FontWeight.Bold)

        // Start Date and Time
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = startDate,
                onValueChange = { startDate = it },
                label = { Text("Start Date") },
                placeholder = { Text("YYYY-MM-DD") },
                modifier = Modifier.weight(1f)
            )
            OutlinedTextField(
                value = startTimeOnly,
                onValueChange = { startTimeOnly = it },
                label = { Text("Start Time") },
                placeholder = { Text("HH:mm") },
                modifier = Modifier.weight(1f)
            )
        }

        // End Date and Time
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = endDate,
                onValueChange = { endDate = it },
                label = { Text("End Date") },
                placeholder = { Text("YYYY-MM-DD") },
                modifier = Modifier.weight(1f)
            )
            OutlinedTextField(
                value = endTimeOnly,
                onValueChange = { endTimeOnly = it },
                label = { Text("End Time") },
                placeholder = { Text("HH:mm") },
                modifier = Modifier.weight(1f)
            )
        }

        Button(
            onClick = {
                scope.launch {
                    isLoading = true
                    try {
                        val response = RetrofitClient.apiService.searchLots(
                            SearchRequest(userId, listOf(lotId), fullStartTime, fullEndTime)
                        )
                        searchResults = response.results
                    } catch (e: Exception) {
                        Toast.makeText(context, "Search failed: ${e.message}", Toast.LENGTH_SHORT).show()
                    } finally {
                        isLoading = false
                    }
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Search Availability")
        }

        HorizontalDivider()

        if (isLoading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(searchResults) { result ->
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = if (selectedResult == result) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { selectedResult = result }
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Lot ID: ${result.lot_id}\nSpots: ${result.available_spots}")
                            Text("$${result.price_per_hour}/hr", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onBack, modifier = Modifier.weight(1f)) {
                Text("Cancel")
            }
            Button(
                onClick = {
                    selectedResult?.let { res ->
                        scope.launch {
                            try {
                                val bookResponse = RetrofitClient.apiService.bookLot(
                                    BookingRequest(
                                        user_id = userId,
                                        lot_id = res.lot_id,
                                        event_id = res.event_id,
                                        start_time = fullStartTime,
                                        end_time = fullEndTime,
                                        price = res.price_per_hour,
                                        is_booking = true
                                    )
                                )
                                if (bookResponse.success) {
                                    onReservationSuccess()
                                } else {
                                    Toast.makeText(context, bookResponse.failure_reason ?: "Booking failed", Toast.LENGTH_SHORT).show()
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                },
                enabled = selectedResult != null,
                modifier = Modifier.weight(1f)
            ) {
                Text("Confirm Booking")
            }
        }
    }
}

@Composable
fun MyReservationsScreen(userId: String, onBack: () -> Unit) {
    var reservations by remember { mutableStateOf<List<ReservationInfo>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    fun fetchReservations() {
        scope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getUserReservations(UserReservationsRequest(userId))
                reservations = response.reservations
            } catch (e: Exception) {
                Toast.makeText(context, "Failed to load reservations", Toast.LENGTH_SHORT).show()
            } finally {
                isLoading = false
            }
        }
    }

    fun formatIsoDate(isoString: String?): String {
        return isoString?.split("T")?.getOrNull(0) ?: "N/A"
    }

    fun formatIsoTime(isoString: String?): String {
        return isoString?.split("T")?.getOrNull(1)?.substringBeforeLast(":") ?: "N/A"
    }

    LaunchedEffect(userId) {
        fetchReservations()
    }

    Scaffold(
        topBar = {
            Box(modifier = Modifier.statusBarsPadding().padding(16.dp)) {
                Text("My Reservations", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
        },
        bottomBar = {
            Button(onClick = onBack, modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                Text("Back")
            }
        }
    ) { padding ->
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (reservations.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No reservations found.")
            }
        } else {
            LazyColumn(modifier = Modifier.padding(padding)) {
                items(reservations) { res ->
                    Card(modifier = Modifier.fillMaxWidth().padding(8.dp)) {
                        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Lot ID: ${res.lot_id}", fontWeight = FontWeight.Bold)
                                Text("Status: ${res.status}")
                                Text("Date: ${formatIsoDate(res.start_time)}")
                                Text("Time: ${formatIsoTime(res.start_time)} - ${formatIsoTime(res.end_time)}")
                                Text("Price: $${res.price_at_booking}")
                            }
                            IconButton(onClick = {
                                scope.launch {
                                    try {
                                        val cancelResponse = RetrofitClient.apiService.cancelReservation(
                                            CancelReservationRequest(userId, res.reservation_id ?: "")
                                        )
                                        if (cancelResponse.success) {
                                            Toast.makeText(context, "Cancelled successfully", Toast.LENGTH_SHORT).show()
                                            fetchReservations()
                                        } else {
                                            Toast.makeText(context, cancelResponse.message ?: "Cancel failed", Toast.LENGTH_SHORT).show()
                                        }
                                    } catch (e: Exception) {
                                        Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }) {
                                Icon(Icons.Default.Delete, contentDescription = "Cancel", tint = MaterialTheme.colorScheme.error)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ReservationSuccessScreen(onBackToHome: () -> Unit, onViewReservations: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Success!", fontSize = 32.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        Spacer(modifier = Modifier.height(8.dp))
        Text("Your reservation was successful")
        Spacer(modifier = Modifier.height(24.dp))
        Button(onClick = onViewReservations, modifier = Modifier.fillMaxWidth()) {
            Text("View My Reservations")
        }
        Spacer(modifier = Modifier.height(8.dp))
        OutlinedButton(onClick = onBackToHome, modifier = Modifier.fillMaxWidth()) {
            Text("Back to Home")
        }
    }
}
