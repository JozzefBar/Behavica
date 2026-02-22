package com.example.behavica.data

import com.example.behavica.R
import android.annotation.SuppressLint
import android.content.Context
import android.provider.Settings
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Source

class AppStartHandler (
    private val context: Context,
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
    private val repo: FirestoreRepository = FirestoreRepository(db, context)
) {

    sealed class StartDestination {
        object EmailCheck : StartDestination()
        data class EmailCheckBlocked(val message: String) : StartDestination()
    }

    fun determineStartDestination(
        onResult: (StartDestination) -> Unit,
        onError: (String) -> Unit
    ){
        repo.ensureAnonAuth(
            onReady = { checkDeviceUsage(onResult, onError) },
            onError = onError
        )
    }

    @SuppressLint("HardwareIds")
    private fun checkDeviceUsage(
        onResult: (StartDestination) -> Unit,
        onError: (String) -> Unit
    ){
        val deviceId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID
        ) ?: run {
            onError(context.getString(R.string.no_device_id))
            return
        }

        db.collection("Users3")
            .whereEqualTo("deviceId", deviceId)
            .limit(1)
            .get(Source.SERVER)
            .addOnSuccessListener { query ->
                if (query.isEmpty) {
                    onResult(StartDestination.EmailCheck)
                } else {
                    onResult(StartDestination.EmailCheckBlocked(context.getString(R.string.device_already_used)))
                }
            }
            .addOnFailureListener { e ->
                onError(context.getString(R.string.error_checking_device, e.message))
            }
    }
}