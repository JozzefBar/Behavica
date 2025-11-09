package com.example.behavica.data

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class AppStartHandler (
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

    private fun checkDeviceUsage(
        onResult: (StartDestination) -> Unit,
        onError: (String) -> Unit
    ){
        val deviceId = auth.currentUser?.uid ?: run {
            onError("No device ID available")
            return
        }

        db.collection("Users3")
            .whereEqualTo("deviceId", deviceId)
            .limit(1)
            .get()
            .addOnSuccessListener { query ->
                if (query.isEmpty) {
                    // Device never used - allow email check
                    onResult(StartDestination.EmailCheck)
                } else
                    // All submissions completed
                    onResult(StartDestination.Ending)
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