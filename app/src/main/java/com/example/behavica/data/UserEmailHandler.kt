package com.example.behavica.data

import android.os.Handler
import android.os.Looper
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthException
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreException
import com.google.firebase.firestore.Source

class UserEmailHandler(
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
    private val auth: FirebaseAuth = FirebaseAuth.getInstance(),
    private val repo: FirestoreRepository = FirestoreRepository(FirebaseFirestore.getInstance())
) {
    // Variables used for debouncing email checks, tracking latest requests, and managing Firebase auth state
    private val handler = Handler(Looper.getMainLooper())
    private var pendingCheck: Runnable? = null
    private var queryToken = 0
    private var lastFinishedToken = -1
    private var authReady = false

    fun ensureAnonAuth(
        onReady: () -> Unit,
        onError: (String) -> Unit
    ) {
        if (auth.currentUser != null) {
            authReady = true
            onReady()
            return
        }
        auth.signInAnonymously()
            .addOnSuccessListener {
                authReady = true
                onReady()
            }
            .addOnFailureListener { e ->
                val msg = (e as? FirebaseAuthException)?.errorCode ?: e.localizedMessage
                onError("Auth failed: $msg")
            }
    }

    fun debounceEmailCheck(
        email: String,
        delayMs: Long = 300,
        onStart: () -> Unit,
        onResult: (String?, String, Boolean) -> Unit,
        onError: (String) -> Unit
    ) {
        pendingCheck?.let { handler.removeCallbacks(it) }
        val token = ++queryToken
        pendingCheck = Runnable {
            if (!authReady) {
                ensureAnonAuth(
                    onReady = { doServerCheck(email.lowercase(), token, onResult, onError, onStart) },
                    onError = onError
                )
            } else {
                doServerCheck(email.lowercase(), token, onResult, onError, onStart)
            }
        }
        handler.postDelayed(pendingCheck!!, delayMs)
    }

    private fun doServerCheck(
        emailLower: String,
        token: Int,
        onResult: (String?, String, Boolean) -> Unit,
        onError: (String) -> Unit,
        onStart: () -> Unit
    ) {
        onStart()
        db.collection("Users2").document(emailLower)
            .get(Source.SERVER)
            .addOnSuccessListener { snap ->
                if (token <= lastFinishedToken) return@addOnSuccessListener
                lastFinishedToken = token

                if (snap.exists()) {
                    val count = (snap.getLong("submissionCount") ?: 0).toInt()
                    val uid = snap.getString("userId")
                    val msg = "This email already has $count submission(s). " +
                            if (!uid.isNullOrBlank()) "User ID: $uid" else "No user ID stored for this email."
                    onResult(uid, msg, true)
                } else {
                    onResult(null, "This email is not in the database yet. A new User ID will be generated after clicking Start.", false)
                }
            }
            .addOnFailureListener { e ->
                if (token <= lastFinishedToken) return@addOnFailureListener
                lastFinishedToken = token
                val code = (e as? FirebaseFirestoreException)?.code?.name ?: e.localizedMessage
                onError("Couldn't check DB: $code")
            }
    }

    fun generateNewUserId(
        onSuccess: (String) -> Unit,
        onError: (String) -> Unit
    ) {
        repo.generateUniqueUserIdOnly(
            onResult = onSuccess,
            onError = onError
        )
    }
}
