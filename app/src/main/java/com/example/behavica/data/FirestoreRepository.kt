package com.example.behavica.data

import android.content.Context
import android.provider.Settings
import android.os.Build
import com.example.behavica.R
import com.example.behavica.model.SensorReading
import com.example.behavica.model.TouchPoint
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions
import com.google.firebase.firestore.Source
import kotlin.random.Random

class FirestoreRepository(
    private val db: FirebaseFirestore,
    private val context: Context,
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
) {

    fun ensureAnonAuth(
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
                onError(context.getString(R.string.auth_failed, e.message))
            }
    }

    fun checkEmailExists(
        email: String,
        onResult: (exists: Boolean, message: String) -> Unit,
        onError: (String) -> Unit
    ){
        db.collection("Users3").whereEqualTo("email", email.lowercase()).limit(1).get(Source.SERVER)
            .addOnSuccessListener { query ->
                if (query.isEmpty) {
                    onResult(false, context.getString(R.string.email_available))
                } else {
                    onResult(true, context.getString(R.string.email_already_registered))
                }
            }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("UNAVAILABLE") == true ->
                        context.getString(R.string.network_unavailable)
                    e.message?.contains("DEADLINE_EXCEEDED") == true ->
                        context.getString(R.string.network_timeout)
                    e.message?.contains("Failed to get documents from server") == true ->
                        context.getString(R.string.network_unavailable)
                    else ->
                        context.getString(R.string.error_checking_email, e.message)
                }
                onError(errorMessage)
            }
    }

    fun generateUniqueUserIdOnly(
        onResult: (userId: String) -> Unit,
        onError: (error: String) -> Unit,
        attemptsLeft: Int = 50
    ) {
        if (attemptsLeft <= 0) {
            onError(context.getString(R.string.could_not_generate_userid))
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
            .whereEqualTo("userId", userId.toInt())
            .limit(1)
            .get(Source.SERVER)
            .addOnSuccessListener { query ->
                onResult(!query.isEmpty)
            }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("UNAVAILABLE") == true ->
                        context.getString(R.string.network_unavailable)
                    e.message?.contains("DEADLINE_EXCEEDED") == true ->
                        context.getString(R.string.network_timeout)
                    else ->
                        context.getString(R.string.failed_to_check_userid, e.localizedMessage)
                }
                onError(errorMessage)
            }
    }

    @android.annotation.SuppressLint("HardwareIds")
    fun createUserMetadata(
        userId: String,
        email: String,
        userAge: Int,
        userGender: String,
        dominantHand: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ){
        val firebaseUid = auth.currentUser?.uid ?: ""

        // Device ID ensures one-time participation per device (similar to fraud prevention).
        val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: ""

        val metadata = hashMapOf(
            "userId" to userId.toInt(),
            "email" to email,
            "createdBy" to firebaseUid,
            "age" to userAge,
            "gender" to userGender,
            "dominantHand" to dominantHand,
            "deviceId" to deviceId,
            "deviceManufacturer" to Build.MANUFACTURER,
            "deviceModel" to Build.MODEL,
            "androidVersion" to Build.VERSION.RELEASE,
            "submissionCount" to 0,
            "createdAt" to FieldValue.serverTimestamp(),
            "timestamp" to System.currentTimeMillis()
        )

        db.collection("Users3").document(userId)
            .set(metadata)
            .addOnSuccessListener { onSuccess() }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("PERMISSION_DENIED") == true -> context.getString(R.string.permission_denied)
                    e.message?.contains("NETWORK_ERROR") == true -> context.getString(R.string.network_error)
                    else -> context.getString(R.string.error_creating_user, e.message)
                }
                onError(errorMessage)
            }
    }

    fun saveSubmission(
        userId: String,
        submissionNumber: Int,
        dragAttempts: Int,
        dragDistance: Float,
        dragPathLength: Float,
        dragDurationSec: Double,
        textRewriteTime: Double,
        averageWordTime: Double,
        textEditCount: Int,
        touchPointsCount: Int,
        touchPoints: List<TouchPoint>,
        keystrokes: List<Map<String, Any>>,
        sensorDataCount: Int,
        sensorData: List<SensorReading>,
        submissionDurationSec: Double,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ){
        val submission = hashMapOf(
            "timestamp" to System.currentTimeMillis(),
            "createdAt" to FieldValue.serverTimestamp(),
            "submissionDurationSec" to submissionDurationSec,
            "dragAttempts" to dragAttempts,
            "dragDistance" to dragDistance,
            "dragPathLength" to dragPathLength,
            "dragDurationSec" to dragDurationSec,
            "textRewriteTime" to textRewriteTime,
            "averageWordTime" to averageWordTime,
            "textEditCount" to textEditCount,
            "touchPointsCount" to touchPointsCount,
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
                    "timestamp" to tp.timestamp,
                    "action" to tp.action,
                    "pointerId" to tp.pointerId,
                    "target" to tp.target
                )
            },
            "sensorDataCount" to sensorDataCount,
            "sensorData" to sensorData.map { sr ->
                mapOf(
                    "timestamp" to sr.timestamp,
                    "accelX" to sr.accelX,
                    "accelY" to sr.accelY,
                    "accelZ" to sr.accelZ,
                    "gyroX" to sr.gyroX,
                    "gyroY" to sr.gyroY,
                    "gyroZ" to sr.gyroZ
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
                    e.message?.contains("PERMISSION_DENIED") == true -> context.getString(R.string.permission_denied)
                    e.message?.contains("NETWORK") == true -> context.getString(R.string.network_error)
                    else -> context.getString(R.string.error_saving_submission, e.message)
                }
                onError(errorMessage)
            }
    }
}