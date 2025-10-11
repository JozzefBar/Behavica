package com.example.behavica.data

import android.os.Build
import com.example.behavica.metrics.FormMetrics
import com.example.behavica.model.TouchPoint
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions
import java.text.SimpleDateFormat
import kotlin.random.Random
import java.util.*

class FirestoreRepository(private val db: FirebaseFirestore) {

    fun generateUniqueUserIdOnly(
        onResult: (userId: String) -> Unit,
        onError: (error: String) -> Unit,
        attemptsLeft: Int = 20
    ) {
        if (attemptsLeft <= 0) {
            onError("Could not generate unique userId.")
            return
        }
        val candidate = Random.nextInt(10000, 100000).toString()        //generate random 5-digit number
        db.collection("Users2").whereEqualTo("userId", candidate).limit(1).get()
            .addOnSuccessListener { q ->
                if (!q.isEmpty) {
                    generateUniqueUserIdOnly(onResult, onError, attemptsLeft - 1)
                } else {
                    onResult(candidate)
                }
            }
            .addOnFailureListener { e -> onError("Failed to check uniqueness: ${e.localizedMessage}") }
    }

    fun submitWithMetrics(
        email: String,
        userAge: Int,
        userGender: String,
        handHeld: String,
        metrics: FormMetrics,
        touchPoints: List<TouchPoint>,
        existingUserId: String?,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        val proceed: (String) -> Unit = { userId ->
            saveSubmission(
                email = email,
                userId = userId,
                userAge = userAge,
                userGender = userGender,
                handHeld = handHeld,
                metrics = metrics,
                touchPoints = touchPoints,
                onSuccess = onSuccess,
                onError = onError
            )
        }

        if (!existingUserId.isNullOrBlank()) {
            proceed(existingUserId)
        } else {
            generateUniqueUserIdOnly(
                onResult = { uid -> proceed(uid) },
                onError = onError
            )
        }
    }

    fun saveSubmission(
        email: String,
        userId: String,
        userAge: Int,
        userGender: String,
        handHeld: String,
        metrics: FormMetrics,
        touchPoints: List<TouchPoint>,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        // creation of timestamp
        val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        dateFormat.timeZone = TimeZone.getDefault()
        val currentTime = dateFormat.format(Date())
        val timestampId = currentTime.replace(" ", "_").replace(":", "-")

        val behaviorData = metrics.buildBehaviorData(touchPoints)

        // create user data structure for Firebase
        val submission = hashMapOf(
            "age" to userAge,
            "gender" to userGender,
            "timestamp" to currentTime,
            "createdAt" to FieldValue.serverTimestamp(),
            "deviceModel" to Build.MODEL,
            "androidVersion" to Build.VERSION.RELEASE,
            "handUsed" to handHeld,
            "behavior" to behaviorData
        )

        val emailDoc = db.collection("Users2").document(email)
        val subDoc = emailDoc.collection(timestampId).document("submission")

        //parent meta: submissionCount
        val parentMeta = mapOf(
            "email" to email,
            "userId" to userId,
            "submissionCount" to FieldValue.increment(1)
        )

        val batch = db.batch()
        batch.set(emailDoc, parentMeta, SetOptions.merge())
        batch.set(subDoc, submission)

        batch.commit()
            .addOnSuccessListener { onSuccess() }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("PERMISSION_DENIED") == true -> "Permission denied. Please check your data."
                    e.message?.contains("NETWORK") == true -> "Network error. Please check your internet connection."
                    else -> "Error saving data: ${e.message}"
                }
                onError(errorMessage)
            }
    }
}
