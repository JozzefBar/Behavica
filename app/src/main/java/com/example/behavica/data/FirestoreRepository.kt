package com.example.behavica.data

import android.content.Context
import android.provider.Settings
import android.os.Build
import com.example.behavica.model.TouchPoint
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions
import java.text.SimpleDateFormat
import kotlin.random.Random
import java.util.*

class FirestoreRepository(private val db: FirebaseFirestore) {

    fun checkEmailExists(
        email: String,
        onResult: (exists: Boolean, message: String) -> Unit,
        onError: (String) -> Unit
    ){
        db.collection("Users3").whereEqualTo("email", email.lowercase()).limit(1).get()
            .addOnSuccessListener { query ->
                if (query.isEmpty) {
                    onResult(false, "Email is available")
                } else {
                    onResult(true, "This email is already registered. Please use a different email.")
                }
            }
            .addOnFailureListener { e ->
                onError("Error checking email: ${e.message}")
            }
    }

    fun generateUniqueUserIdOnly(
        onResult: (userId: String) -> Unit,
        onError: (error: String) -> Unit,
        attemptsLeft: Int = 50
    ) {
        if (attemptsLeft <= 0) {
            onError("Could not generate unique userId after 50 attempts.")
            return
        }

        val candidate = Random.nextInt(10000, 100000).toString()

        checkUserIdExists(
            userId = candidate,
            onResult = { exists ->
                if (exists) {
                    generateUniqueUserIdOnly(onResult, onError, attemptsLeft - 1)
                } else {
                    onResult(candidate)
                }
            },
            onError = { error ->
                onError(error)
            }
        )
    }

    private fun checkUserIdExists(
        userId: String,
        onResult: (Boolean) -> Unit,
        onError: (String) -> Unit
    ) {
        db.collection("Users3")
            .whereEqualTo("userId", userId)
            .limit(1)
            .get()
            .addOnSuccessListener { query ->
                onResult(!query.isEmpty)
            }
            .addOnFailureListener { e ->
                onError("Failed to check userId: ${e.localizedMessage}")
            }
    }

    @android.annotation.SuppressLint("HardwareIds")
    fun createUserMetadata(
        context: Context,
        userId: String,
        email: String,
        userAge: Int,
        userGender: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ){
        val dateFormat = SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault())
        dateFormat.timeZone = TimeZone.getTimeZone("Europe/Bratislava")
        val currentTime = dateFormat.format(Date())

        // Device ID ensures one-time participation per device (similar to fraud prevention).
        val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: ""

        val metadata = hashMapOf(
            "userId" to userId,
            "email" to email,
            "age" to userAge,
            "gender" to userGender,
            "deviceId" to deviceId,
            "deviceManufacturer" to Build.MANUFACTURER,
            "deviceModel" to Build.MODEL,
            "androidVersion" to Build.VERSION.RELEASE,
            "submissionCount" to 0,
            "createdAt" to FieldValue.serverTimestamp(),
            "timestamp" to currentTime
        )

        db.collection("Users3").document(userId)
            .set(metadata)
            .addOnSuccessListener { onSuccess() }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("PERMISSION_DENIED") == true -> "Permission denied."
                    e.message?.contains("NETWORK_ERROR") == true -> "Network error."
                    else -> "Error creating user: ${e.message}"
                }
                onError(errorMessage)
            }
    }

    fun saveSubmission(
        userId: String,
        submissionNumber: Int,
        handHeld: String,
        dragCompleted: Boolean,
        dragAttempts: Int,
        dragDistance: Float,
        dragPathLength: Float,
        dragDurationSec: Double,
        textRewriteCompleted: Boolean,
        textRewriteTime: Double,
        textEditCount: Int,
        checkboxChecked: Boolean,
        touchPoints: List<TouchPoint>,
        keystrokes: List<Map<String, Any>>,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ){
        val dateFormat = SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.getDefault())
        dateFormat.timeZone = TimeZone.getTimeZone("Europe/Bratislava")
        val currentTime = dateFormat.format(Date())

        val submission = hashMapOf(
            "handUsed" to handHeld,
            "timestamp" to currentTime,
            "createdAt" to FieldValue.serverTimestamp(),
            "dragCompleted" to dragCompleted,
            "dragAttempts" to dragAttempts,
            "dragDistance" to dragDistance,
            "dragPathLength" to dragPathLength,
            "dragDurationSec" to dragDurationSec,
            "textRewriteCompleted" to textRewriteCompleted,
            "textRewriteTime" to textRewriteTime,
            "textEditCount" to textEditCount,
            "checkboxChecked" to checkboxChecked,
            "touchPointsCount" to touchPoints.size,
            "touchPoints" to touchPoints.map{ tp ->
                mapOf(
                    "pressure" to tp.pressure,
                    "size" to tp.size,
                    "x" to tp.x,
                    "y" to tp.y,
                    "rawX" to tp.rawX,
                    "rawY" to tp.rawY,
                    "touchMajor" to tp.touchMajor,
                    "touchMinor" to tp.touchMinor,
                    "timestampTime" to tp.timestampTime,
                    "timestampEpochMs" to tp.timestampEpochMs,
                    "action" to tp.action,
                    "pointerId" to tp.pointerId,
                    "target" to tp.target
                )
            },
            "keystrokes" to keystrokes,
        )

        val userDoc = db.collection("Users3").document(userId)
        val submissionDoc = userDoc.collection("submissions").document("submission$submissionNumber")

        val batch = db.batch()
        batch.set(submissionDoc, submission)
        batch.set(userDoc, mapOf("submissionCount" to FieldValue.increment(1)), SetOptions.merge())

        batch.commit()
            .addOnSuccessListener { onSuccess() }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("PERMISSION_DENIED") == true -> "Permission denied."
                    e.message?.contains("NETWORK") == true -> "Network error."
                    else -> "Error saving submission: ${e.message}"
                }
                onError(errorMessage)
            }
    }
}