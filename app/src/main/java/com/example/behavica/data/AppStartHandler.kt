package com.example.behavica.data

import android.annotation.SuppressLint
import android.content.Context
import android.provider.Settings
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class AppStartHandler (
    private val context: Context,
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
) {

    sealed class StartDestination {
        object EmailCheck : StartDestination()
        object Ending : StartDestination()
    }

    fun determineStartDestination(
        onResult: (StartDestination) -> Unit,
        onError: (String) -> Unit
    ){
        ensureAnonAuth(
            onReady = { checkDeviceUsage(onResult, onError) },
            onError = onError
        )
    }

    @SuppressLint("HardwareIds")  // Legitimate research use-case
    private fun checkDeviceUsage(
        onResult: (StartDestination) -> Unit,
        onError: (String) -> Unit
    ){
        // We need a persistent device identifier to ensure one-time participation per device.
        val deviceId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID
        ) ?: run {
            onError("No device ID available")
            return
        }

        db.collection("Users3")
            .whereEqualTo("deviceId", deviceId)
            .limit(1)
            .get()
            .addOnSuccessListener { query ->
                if (query.isEmpty) {
                    // Device never used
                    onResult(StartDestination.EmailCheck)
                } else {
                    // Device already used - always block
                    onResult(StartDestination.Ending)
                }
            }
            .addOnFailureListener { e ->
                onError("Error checking device: ${e.message}")
            }
    }

    private fun ensureAnonAuth(
        onReady: () -> Unit,
        onError: (String) -> Unit
    ) {
        if (auth.currentUser != null) {
            onReady()
            return
        }

        auth.signInAnonymously()
            .addOnSuccessListener { onReady() }
            .addOnFailureListener { e ->
                onError("Auth failed: ${e.message}")
            }
    }
}