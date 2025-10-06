package com.example.behavica.data

import android.os.Build
import com.example.behavica.metrics.FormMetrics
import com.example.behavica.model.TouchPoint
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions
import java.text.SimpleDateFormat
import java.util.*

class FirestoreRepository(private val db: FirebaseFirestore) {

    fun submit(
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

        val behaviorData = metrics.buildBehaviorData(userId, touchPoints)

        // create user data structure for Firebase
        val submission = hashMapOf(
            "userId" to userId,
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

        //parent meta: submissionCount + lastSubmissionAt
        val parentMeta = mapOf(
            "email" to email,
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
